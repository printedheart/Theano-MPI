from mpi4py import MPI
import numpy as np
import pycuda.gpuarray as gpuarray
import theano
import theano.misc.pycuda_init
import theano.misc.pycuda_utils

from helper_funcs import bufint, dtype_to_mpi

class BSP_Exchanger(object):
    '''
    model parameter exchanger during BSP weight exchanging
    '''
    def __init__(self, config, drv, ctx, model):

        self.drv = drv
        self.ctx = ctx
        self.comm = config['comm']

        self.size = config['size']
        
        self.exch_strategy = config['exch_strategy']

        self.train_mode = config['train_mode']
        # self.cuda_aware = config['cuda_aware']
        
        # TODO make sure exchanger class doesn't keep a self copy of model, only the reference to its param list
        self.param_list = model.params
        self.vels = model.vels
        self.vels2 = model.vels2

        self.avg_func_list = []
        
        if self.train_mode == 'cdd' and self.exch_strategy == 'ar':
            
            from exchanger_strategy import Exch_allreduce
            self.exch = Exch_allreduce(self.comm, avg=False)
            self.exch.prepare(self.vels, self.vels2)
            
        elif self.train_mode == 'cdd' and self.exch_strategy == 'copper':
            
            from exchanger_strategy import Exch_copper
            self.exch = Exch_copper(self.comm, avg=False)
            self.exch.prepare(self.ctx, self.drv, self.vels, self.vels2)
            
        elif self.train_mode == 'cdd' and self.exch_strategy == 'copper16':
            
            from exchanger_strategy import Exch_copper16
            self.exch = Exch_copper16(self.comm, avg=False)
            self.exch.prepare(self.ctx, self.drv, self.vels, self.vels2)
            
        elif self.train_mode == 'cdd' and self.exch_strategy == 'asa32':
            
            from exchanger_strategy import Exch_asa32
            self.exch = Exch_asa32(self.comm, avg=False)
            self.exch.prepare(self.ctx, self.drv, self.vels, self.vels2)
            
        elif self.train_mode == 'cdd' and self.exch_strategy == 'asa16':
            
            from exchanger_strategy import Exch_asa16
            self.exch = Exch_asa16(self.comm, avg=False)
            self.exch.prepare(self.ctx, self.drv, self.vels, self.vels2)
        
        
         
        elif self.train_mode == 'avg' and self.exch_strategy == 'ar':
            
            from exchanger_strategy import Exch_allreduce
            self.exch = Exch_allreduce(self.comm)
            self.exch.prepare(self.param_list)
            
        elif self.train_mode == 'avg' and self.exch_strategy == 'copper':
            
            from exchanger_strategy import Exch_copper
            self.exch = Exch_copper(self.comm)
            self.exch.prepare(self.ctx, self.drv, self.param_list)
            
        elif self.train_mode == 'avg' and self.exch_strategy == 'copper16':
            
            from exchanger_strategy import Exch_copper16
            self.exch = Exch_copper16(self.comm)
            self.exch.prepare(self.ctx, self.drv, self.param_list)
            
        elif self.train_mode == 'avg' and self.exch_strategy == 'asa32':
            
            from exchanger_strategy import Exch_asa32
            self.exch = Exch_asa32(self.comm)
            self.exch.prepare(self.ctx, self.drv, self.param_list)
            
        elif self.train_mode == 'avg' and self.exch_strategy == 'asa16':
            
            from exchanger_strategy import Exch_asa16
            self.exch = Exch_asa16(self.comm)
            self.exch.prepare(self.ctx, self.drv, self.param_list)
                

    def exchange(self):
        
        # average w
        if self.train_mode == 'avg' and self.size > 1:
            
            if self.exch_strategy == 'ar':
                
                self.exch.exchange()

            elif self.exch_strategy == 'copper':
                
                self.exch.exchange()
                    
            elif self.exch_strategy == 'asa32': 

                self.exch.exchange()          

            elif self.exch_strategy == 'asa16':
                
                self.exch.exchange()
                
            elif self.exch_strategy == 'copper16':
            
                self.exch.exchange()

        # sum delta w
        elif self.train_mode == 'cdd' and self.size > 1:
            
            if self.exch_strategy == 'ar':
                
                self.exch.exchange()
                
            elif self.exch_strategy == 'copper':
                
                self.exch.exchange()
                
            elif self.exch_strategy == 'asa32':

                self.exch.exchange()
                
            elif self.exch_strategy == 'asa16':
                
                self.exch.exchange()
                
            elif self.exch_strategy == 'copper16':
            
                self.exch.exchange()
                
                
        
class EASGD_Exchanger(object):
    '''
    model parameter exchanger during EASGD weight exchanging (with sync rule intergrated)
    '''
    def __init__(self, config, drv, param_list, etype):
        
        self.etype = etype
        self.drv = drv
        self.param_list = param_list

        self.dest = 0 # size is 1 on both side of this intercomm, so server_rank=0, worker_rank=0
        # TODO not sure if alpha = 1.0/config['size'] is better
        

        if self.etype == 'server':
            self.prepare_server()
            self.alpha = config['server_alpha']
        elif self.etype == 'worker':
            self.prepare_worker()
            self.alpha = config['worker_alpha']
            
        self.update_func = self.mk_update_func()
        self.comm = None
            
        
    def prepare_server(self):
        
        self.g_param_list = self.param_list
        self.g_param_ga_list = []
        self.w_param_ga_list = []
        self.w_param_list = []

        for param in self.param_list:
            np_param = param.get_value()
            w_param = theano.shared(np_param)
            self.w_param_list.append(w_param)
            w_param_ga = gpuarray.GPUArray(np_param.shape,np_param.dtype)
            self.w_param_ga_list.append(w_param_ga)
            g_param_ga = gpuarray.GPUArray(np_param.shape,np_param.dtype)
            self.g_param_ga_list.append(g_param_ga)
            
    def prepare_worker(self):
        
        self.w_param_list = self.param_list
        self.w_param_ga_list = []
        self.g_param_ga_list = []
        self.g_param_list = []

        for param in self.param_list:
            
            np_param = param.get_value()
            g_param = theano.shared(np_param)
            self.g_param_list.append(g_param)
            g_param_ga = gpuarray.GPUArray(np_param.shape,np_param.dtype)
            self.g_param_ga_list.append(g_param_ga)
            w_param_ga = gpuarray.GPUArray(np_param.shape,np_param.dtype)
            self.w_param_ga_list.append(w_param_ga)
            
    def mk_update_func(self):
        
        w_updates = []
        g_updates = []
        for w_param, g_param in zip(self.w_param_list, self.g_param_list):
             w_updates.append(w_param - self.alpha * (w_param - g_param))
             g_updates.append(g_param + self.alpha * (w_param - g_param))
            
        updates = zip(self.w_param_list, w_updates) + \
                        zip(self.g_param_list, g_updates)
        
        return theano.function([], updates=updates)
        
        
    def exchange(self):
        
        # server and worker send param to each other
        
        # this function needs the worker to send an 'exchange' message 
        # to the server through REQ-REP socket first.
        
        assert self.comm != None
        
        if self.etype == 'server':
            
            # copy weight from g_param to g_param_ga
            for g_param, g_param_ga in \
                            zip(self.g_param_list, self.g_param_ga_list):

                param_ga = \
                 theano.misc.pycuda_utils.to_gpuarray(g_param.container.value)

                self.drv.memcpy_dtod(g_param_ga.ptr,
                                      param_ga.ptr,
                                      param_ga.dtype.itemsize *
                                      param_ga.size)
                                      
            # Sendrecv(self, sendbuf, int dest=0, int sendtag=0, recvbuf=None, int source=0, int recvtag=0, Status status=None)
            
            for g_param_ga, w_param_ga in zip(self.g_param_ga_list, self.w_param_ga_list):
                self.comm.Sendrecv(sendbuf = [bufint(g_param_ga), MPI.FLOAT], dest = self.dest,
                                   recvbuf = [bufint(w_param_ga), MPI.FLOAT], source = self.dest,
                                   )
                                   
            # copy weight from w_param_ga to w_param
            for w_param, w_param_ga in \
                            zip(self.w_param_list, self.w_param_ga_list):

            	param_ga = \
                 theano.misc.pycuda_utils.to_gpuarray(w_param.container.value)

            	self.drv.memcpy_dtod(param_ga.ptr,
                                      w_param_ga.ptr,
                                      w_param_ga.dtype.itemsize *
                                      w_param_ga.size)
                               
                               
        elif self.etype == 'worker':
            
            # copy weight from w_param to w_param_ga
            for w_param, w_param_ga in \
                            zip(self.w_param_list, self.w_param_ga_list):

                param_ga = \
                 theano.misc.pycuda_utils.to_gpuarray(w_param.container.value)

                self.drv.memcpy_dtod(w_param_ga.ptr,
                                      param_ga.ptr,
                                      param_ga.dtype.itemsize *
                                      param_ga.size)
                                      
            # Sendrecv(self, sendbuf, int dest=0, int sendtag=0, recvbuf=None, int source=0, int recvtag=0, Status status=None)
            
            for w_param_ga, g_param_ga in zip(self.w_param_ga_list, self.g_param_ga_list):
                self.comm.Sendrecv(sendbuf = [bufint(w_param_ga), MPI.FLOAT], dest = self.dest,
                                   recvbuf = [bufint(g_param_ga), MPI.FLOAT], source = self.dest,
                                   )
                                   
            # copy weight from w_param_ga to w_param
            for g_param, g_param_ga in \
                            zip(self.g_param_list, self.g_param_ga_list):

            	param_ga = \
                 theano.misc.pycuda_utils.to_gpuarray(g_param.container.value)

            	self.drv.memcpy_dtod(param_ga.ptr,
                                      g_param_ga.ptr,
                                      g_param_ga.dtype.itemsize *
                                      g_param_ga.size)
                                      
        self.update_func()
            
        self.comm = None
        
    def copy_to_local(self):
        
        assert self.comm != None
        
        if self.etype == 'server':
            # copy weight from g_param to g_param_ga
            for g_param, g_param_ga in \
                            zip(self.g_param_list, self.g_param_ga_list):

                param_ga = \
                 theano.misc.pycuda_utils.to_gpuarray(g_param.container.value)

                self.drv.memcpy_dtod(g_param_ga.ptr,
                                      param_ga.ptr,
                                      param_ga.dtype.itemsize *
                                      param_ga.size)
                                      
            # Send(self, buf, int dest=0, int tag=0)
            
            
            mpitp = dtype_to_mpi(self.g_param_ga_list[0].dtype)
            
            for g_param_ga in self.g_param_ga_list:
                
                self.comm.Send(buf = [bufint(g_param_ga), mpitp], dest = self.dest)
            
        elif self.etype == 'worker':
            
            mpitp = dtype_to_mpi(self.w_param_ga_list[0].dtype)
            
            for w_param_ga in self.w_param_ga_list:
                
                self.comm.Recv(buf = [bufint(w_param_ga), mpitp], source = self.dest)
                
            # copy weight from w_param_ga to w_param
            for w_param_ga, w_param in \
                            zip(self.w_param_ga_list, self.w_param_list):

                param_ga = \
                 theano.misc.pycuda_utils.to_gpuarray(w_param.container.value)

                self.drv.memcpy_dtod(w_param_ga.ptr,
                                      param_ga.ptr,
                                      param_ga.dtype.itemsize *
                                      param_ga.size)
        self.comm = None
                
                
        
    

 
        
        


