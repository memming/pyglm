from glm import *
from components.network import *

class Population:
    """
    Population connected GLMs.
    """
    def __init__(self, model):
        """
        Initialize the network GLM with given model. What needs to be set?
        """
        self.model = model
        self.N = model['N']

        # Create a network model to connect the GLMs
        self.network = Network(model)

        # Create a single GLM that is shared across neurons
        # This is to simplify the model and reuse parameters. 
        # Basically it speeds up the gradient calculations since we 
        # can manually leverage conditional independencies among GLMs
        self.glm = Glm(model, self.network)

    def compute_log_p(self, vars):
        """ Compute the log joint probability under a given set of variables
        """
        lp = 0.0

        # Get set of symbolic variables
        syms = self.get_variables()

        lp += seval(self.network.log_p,
                    syms['net'],
                    vars['net'])
        for n in np.arange(self.N):
            nvars = self.extract_vars(vars, n)
            lp += seval(self.glm.log_p,
                        syms,
                        nvars)

        return lp

    def eval_state(self, vars):
        """ Evaluate the population state expressions given the parameters, 
            e.g. the stimulus response curves from the basis function weights.
        """
        # Get set of symbolic variables
        syms = self.get_variables()

        # Get the symbolic state expression to evaluate
        state_vars = self.get_state()
        state = {}
        state['net'] = self._eval_state_helper(syms['net'], 
                                                  state_vars['net'], 
                                                  vars['net'])

        glm_states = []
        for n in np.arange(self.N):
            nvars = self.extract_vars(vars, n)
            glm_states.append(self._eval_state_helper(syms,
                                                      state_vars['glm'], 
                                                      nvars))
        state['glms'] = glm_states
        return state

    def _eval_state_helper(self, syms, d, vars):
        """ Helper function to recursively evaluate state variables
        """
        state = {}
        for (k,v) in d.items():
            if isinstance(v,dict):
                state[k] = self._eval_state_helper(syms, v, vars)
            else:
                state[k] = seval(v, syms, vars)
        return state
        
    def get_variables(self):
        """ Get a list of all variables
        """
        v = {}
        v['net'] = self.network.get_variables()
        v['glm'] = self.glm.get_variables()
        return v

    def sample(self):
        """
        Sample parameters of the GLM from the prior
        """
        v = {}
        v['net'] = self.network.sample()
        v['glms'] =[]
        for n in range(self.N):
            xn = self.glm.sample()
            xn['n'] = n
            v['glms'].append(xn)

        return v

    def extract_vars(self, vals, n):
        """ Hacky helper function to extract the variables for only the
         n-th GLM.
        """

        newvals = {}
        for (k,v) in vals.items():
            if k=='glms':
                newvals['glm'] = v[n]
            else:
                newvals[k] = v
        return newvals

    def get_state(self):
        """ Get the 'state' of the system in symbolic Theano variables
        """
        state = {}
        state['net'] = self.network.get_state()
        state['glm'] = self.glm.get_state()

        return state

    def set_data(self, data):
        """
        Condition on the data
        """
        self.network.set_data(data)
        self.glm.set_data(data)

    def simulate(self, vars,  (T_start,T_stop), dt):
        """ Simulate spikes from a network of coupled GLMs
        :param glms - the GLMs to sample, one for each neuron
        :type glms    list of N GLMs
        :param vars - the variables corresponding to each GLM
        :type vars    list of N variable vectors
        :param dt    - time steps to simulate

        :rtype TxN matrix of spike counts in each bin
        """
        # Initialize the background rates
        N = self.model['N']
        assert np.mod(T_start,dt) < 1**-16, "T_start must be divisble by dt"
        assert np.mod(T_stop,dt) < 1**-16, "T_stop must be divisble by dt"
        t = np.arange(T_start, T_stop, dt)
        t_ind = np.arange(int(T_start/dt), int(T_stop/dt))
        assert len(t) == len(t_ind)
        nT = len(t)

        # Get set of symbolic variables
        syms = self.get_variables()\

        # Initialize the background rate
        X = np.zeros((nT,N))
        for n in np.arange(N):
#             X[:,n] = self.glm.bias_model.f_I_bias(*vars[n+1])
            nvars = self.extract_vars(vars, n)
            X[:,n] = seval(self.glm.bias_model.I_bias,
                           syms,
                           nvars)

        # Add stimulus induced currents if given
        for n in np.arange(N):
            #X[:,n] += self.glm.bkgd_model.f_I_stim(*vars[n+1])[t_ind]
            nvars = self.extract_vars(vars, n)
            X[:,n] += seval(self.glm.bkgd_model.I_stim,
                            syms,
                            nvars)

        print "Max background rate: %f" % np.exp(np.max(X))

        # Get the impulse response functions
        imps = []
        for n_post in np.arange(N):
            nvars = self.extract_vars(vars, n_post)
            imps.append(seval(self.glm.imp_model.impulse,
                                  syms,
                                  nvars))
        imps = np.transpose(np.array(imps), axes=[1,0,2])
        T_imp = imps.shape[2]

        # Debug: compute effective weights
        tt_imp = dt*np.arange(T_imp)
        Weff = np.trapz(imps, tt_imp, axis=2)
        print "Effective impulse weights: "
        print Weff


        # Iterate over each time step and generate spikes
        S = np.zeros((nT,N))
        acc = np.zeros(N)
        thr = -np.log(np.random.rand(N))

        for t in np.arange(nT):
            # Update accumulator
            if np.mod(t,10000)==0:
                print "Iteration %d" % t
            # TODO Handle nonlinearities with variables
            lam = np.array(map(lambda n: self.glm.nlin_model.f_nlin(X[t,n]),
                           np.arange(N)))
            acc = acc + lam*dt

            # Spike if accumulator exceeds threshold
            i_spk = acc > thr
            S[t,i_spk] += 1
            n_spk = np.sum(i_spk)

            # Compute the length of the impulse response
            t_imp = np.minimum(nT-t-1,T_imp)

            # Get the instantaneous connectivity
            # TODO Handle time varying weights
            At = np.tile(np.reshape(seval(self.network.graph.A,
                                          syms['net'],
                                          vars['net']),
                                    [N,N,1]),
                         [1,1,t_imp])
            Wt = np.tile(np.reshape(seval(self.network.weights.W,
                                          syms['net'],
                                          vars['net']),
                                    [N,N,1]),
                         [1,1,t_imp])

            # Iterate until no more spikes
            while n_spk > 0:
                # Add weighted impulse response to activation of other neurons)
                X[t+1:t+t_imp+1,:] += np.sum(At[i_spk,:,:t_imp] *
                                             Wt[i_spk,:,:t_imp] *
                                             imps[i_spk,:,:t_imp],0).T

                # Subtract threshold from the accumulator
                acc -= thr*i_spk
                acc[acc<0] = 0

                # Set new threshold after spike
                thr[i_spk] = -np.log(np.random.rand(n_spk))

                i_spk = acc > thr
                S[t,i_spk] += 1
                n_spk = np.sum(i_spk)

                if np.any(S[t,:]>10):
                    import pdb
                    pdb.set_trace()
                    raise Exception("More than 10 spikes in a bin! Decrease variance on impulse weights or decrease simulation bin width.")
        # DEBUG:
        tt = dt * np.arange(nT)
        lam = np.zeros_like(X)
        for n in np.arange(N):
            lam[:,n] = self.glm.nlin_model.f_nlin(X[:,n])

        print "Max firing rate (post sim): %f" % np.max(lam)
        E_nS = np.trapz(lam,tt,axis=0)
        nS = np.sum(S,0)

        print "Sampled %s spikes." % str(nS)
        print "Expected %s spikes." % str(E_nS)

        if np.any(np.abs(nS-E_nS) > 3*np.sqrt(E_nS)):
            print "ERROR: Actual num spikes (%d) differs from expected (%d) by >3 std." % (E_nS,nS)

        return S,X

