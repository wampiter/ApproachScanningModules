import numpy as np
import qt
from approachimagingparams import *
from taskclasses import *
import msvcrt

def measure(feedback = False, xvec = np.zeros(1), yvec = np.zeros(1), 
            angle = 0.0, repeat = False):
    '''
    Takes an appraoch curve measurement. Aborts with 'q' (or stop)
    in non-feedback, 'u' and 'd' will move stage up and down
    
    Kwargs:
    feedback: whether or not to use feedback
    xvec: fast scan vector (numpy array)for 1D and 2D scans, false for 0D
    yvec: slow scan vector (numpy array)for 2D scans, false for 1D and 0D
    angle: measurement ange (in radians)
    repeat: whether to continuously repeat measurement until 'q' is pressed
    '''
       
    
    if len(yvec) > 1 and not len(xvec) > 1:
        logging.error('Cannot have slow but not fast scan vector')
        return
        
    reload(approachimagingparams) # in case param has been changed 
    
    scanx=False;scany=False
    if len(yvec) > 1:
        scany = True
    if len(xvec) > 1:
        scanx = True
        
    qt.mstart()
    
    #Reset instrument (or initialize if not already)
    if qt.instruments.get_instruments_by_type('NI_DAQ'):
        daq = qt.instruments.get_instruments_by_type('NI_DAQ')[0]
        daq.reset()
    else:
        #This reset the device implicitely:
        daq = qt.instruments.create('daq', 'NI_DAQ', id = 'Dev1')
    
    #Check voltage at which z has been left
    zstart = daq.get_parameters['ao0']['value']
    if not zstart:
        daq.set_ao0(0.0)
        zstart = 0.0        
        
    #Prepare approach data structure to store absolutely all raw data:
    approach_data = qt.Data(name='approach_curves')
    approach_data.add_coordinate('sample')
    approach_data.add_coordinate('x [mV]')
    approach_data.add_coordinate('y [mV]')
    approach_data.add_value('z [mV]')
    approach_data.add_value('MIM-C [V]')
    approach_data.add_value('MIM-R [V]')
    approach_data.mimcplot = qt.Plot2D(approach_data, name='MIM-C [V]', 
                                       coorddim = 0, valdim = 3)
    appraoch_data.mimrplot = qt.Plot2D(approach_data, name='MIM-R [V]',
                                       coorddim = 0, valdim = 4)
    approach_data.create_file()
    approach_data.copy_file('appraochimaging.py')
    approach_data.copy_file('approachimagingparams.py')
    
    #Prepare spatial data structures for "normal" scan data:
    if scanx:
        spatial_data_right = qt.Data(name = 'spatial_data_right')
        spatial_data_left = qt.Data(name = 'spatial_data_left')
        spatial_data = [spatial_data_right, spatial_data_left]
        for data_obj in spatial_data:
            data_obj.add_coordinate('x [mV]')
            data_obj.add_coordinate('y [mV]')
            data_obj.add_value('z [mV]')
            data_obj.add_value('MIM-C [V]')
            data_obj.add_value('MIM-R [V]')
            data_obj.topoplot2d = qt.Plot2D(spatial_data,
                                            name = 'topography linecuts')
            data_obj.mimcplot2d = qt.Plot2D(spatial_data,
                                            name = 'MIM-C linecuts', 
                                            valdim = 3)
            data_obj.mimrplot2d = qt.Plot2D(spatial_data,
                                            name = 'MIM-R linecuts', 
                                            valdim = 4)
            if scany:
                data_obj.topoplot3d = qt.Plot3D(spatial_data, 
                                                name = 'topography')
                data_obj.mimcplot3d = qt.Plot3D(spatial_data, 
                                                name = 'MIM-C', valdim = 3)
                data_obj.mimrplot3d = qt.Plot3D(spatial_data, name = 'MIM-R', 
                                                valdim = 4)
            data_obj.create_file()
    
    #Create task which applies steady z-perterbation 
    zactask = AcOutTask(3, SAMPLES, SAMPLERATE, sync = True)    
    zacdata = GenSineWave(samples,amplitude,phase)
    zactask.set_signal(zacdata)
    

    xvec = np.append(xvec,xvec[::-1])
    #For yscan, add another xval to allow break of 1 appraoch while y moves
    xvec = np.append(xvec[0],xvec)
    #This works even for len(xvec)=1 because len(xvec) was doubled.
    xtask = AcOutTask(1, len(xvec), SAMPLERATE/SAMPLES, sync = True)
    xtask.set_signal(xvec)
    
    ytask = DcOutTask(2)
    ztask = DcOutTask(0)
    
    maintask = mimCalbackTask([4,5], SAMPLES, SAMPLERATE, zstart, feedback)
    
    
    
    maintask.userin = False
    while maintask.userin != 'q':
        if msvcrt.kbhit():
            maintask.userin = msvcrt.getch()
        try:
            qt.msleep(.5)
        except:
            logging.warning('Live plotting race condition caused exception.')
    
    print('%i approaches completed' % maintask.callcounter)
    
    maintask.StopTask()
    zactask.StopTask()
    xtask.StopTask()
    ytask.StopTask()
    ztask.StopTask()
    
    maintask.ClearTask()
    zactask.ClearTask()
    xtask.ClearTask()
    ytask.ClearTask()
    ztask.ClearTask()
    
    qt.msleep(.1)
    
    approach_data.close_file()
    for data_obj in spatial_data:
        data_obj.close_file()
    qt.mend()


class mimCallbackTask(AnalogInCallbackTask):
    '''
    Creates (but does not start) task which runs continuously, executing 
    callback code every time an approach curve is taken

    Args:
        channels: list of input channels to use, first C then R
        samples
        samperate
        zstart: z-voltage at which to begin
        feedback: whether or not to use topography (z) feedback
    '''
    def __init__(self, channels, samples, samplerate, zstart, feedback):
        AnalogInCallbackTask.__init__(self, channels, samples, samplerate)
        self.z = zstart
        self.feedback = feedback
        self.userin = False # stores whether task has been interrupted by user
        self.callcounter = 0 # iterates each approach curve (callback)

    def EveryNCallback(self):
        AnalogInCallbackTask.EveryNCallback(self)      
        if self.callcounter % len(xvec) == 0:
            yindex = self.callcounter/len(xvec)
            if yindex >= len(yvec) and not repeat:
                self.userin = 'q'
                print 'Completed scan'
            else:
                #For non-yscan casese the following line will remain yvec[0]
                self.y = yvec[self.callcounter/len(xvec) % len(yvec)]
                ytask.set_voltge(self.y)
                print('y set to %f volts.' % self.y)
                for data_obj in spatial_data:
                    data_obj.new_block()
        else:
            cdata = self.data[0:SAMPLES]
            rdata = self.data[SAMPLES:2*SAMPLES]
            
            if self.feedback:
                #take derivative and smooth:
                self.datadiff = np.diff(movingaverage(cdata,INNER_WINDOW)) 
                self.datadiff = movingaverage(self.datadiff,OUTER_WINDOW)
                self.datadiff[0:OUTER_WINDOW/2]=0 # Zero out data borked by smoothing
                self.datadiff[len(self.datadiff)-OUTER_WINDOW/2:len(self.datadiff)]=0#..
                #Sample at which contact occurs            
                minarg = np.argmin(self.datadif) 
                
                #increment z proportional to offset of contact to make negfeedback:
                if (minarg > LOWER_SAMPLE_THRESHOLD
                    and minarg < UPPER__SAMPLE_THRESHOLD #ensure minarg in window
                    and np.amin(self.datad)<MAGNITUDE_THRESHOLD):
                        self.z += (minarg - CONTACT_SAMPLE)*FEEDBACK_GAIN
            else: # if not in feedback mode
                if self.userin == 'u':
                    self.z += Z_STEP #step up
                    self.userin = False
                elif self.userin == 'd':
                    self.z -= Z_STEP #step down
                    self.userin = False
        
            #Check that Z is within limits
            if self.z > Z_MAX:
                self.z = X_MAX
                logging.error('Reached maximum allowable value')
            elif self.z < Z_MIN:
                self.z = Z_MIN
                logging.error('Reached minimum allowable value')
        
            ztask.set_voltage(self.z)

            try:
                approach_data.add_data_point(arange(SAMPLES),
                                             xvec[self.callcounter] * 1.0e3\
                                                 * ones(SAMPLES),
                                             self.y * 1.0e3 * ones(SAMPLES),
                                             self.z * 1.0e3 * ones(SAMPLES),
                                             mimc, mimr)
                approach_data.new_block()
            except:
                logging.warning('Failed to record approach curve')
            try:
                mimCabs = np.mean(self.data[FAR_FIRST_SAMP:FAR_LAST_SAMP])\
                    - np.mean(self.data[CLOSE_FIRST_SAMP:CLOSE_LAST_SAMP])
                mimRabs = np.mean(self.datar[FAR_FIRST_SAMP:FAR_LAST_SAMP])\
                    - np.mean(self.datar[CLOSE_FIRST_SAMP:CLOSE_LAST_SAMP])
                
                #If we're in the right-going segmet
                if ((self.callcounter % len(xvec)) - 1) < (len(xvec) - 1) / 2:
                    spatial_data_current = spatial_data_right
                else:
                    spatial_data_current = spatial_data_left
                    
                spatial_data_current.add_data_point(xvec[self.callcounter] * 1.0e3,
                                                    self.y * 1.0e3, self.z * 1.0e3,
                                                    mimCabs, mimRabs)
            except:
                logging.warning('Failed to record point data')
            
        self.callcounter += 1