# Run as script using 'python -m test.synth'
from glm_shared import *
from models.model_factory import *
from inference.coord_descent import coord_descent

def plot_results(network_glm, x_trues, x_opts):
    """ Plot the inferred stimulus tuning curves and impulse responses
    """
    import matplotlib
    matplotlib.use('Agg')       # To enable saving remotely
    import matplotlib.pyplot as plt

    true_state = network_glm.get_state(x_trues)
    opt_state = network_glm.get_state(x_opts)

    N = network_glm.N
    
    # Plot the inferred connectivity matrix
    f = plt.figure()
    plt.subplot(1,2,1)
    W_true = true_state['net']
    W_inf = opt_state['net']
    W_max = np.amax(np.maximum(np.abs(W_true),np.abs(W_inf)))
    px_per_node = 10
    plt.imshow(np.kron(W_true,np.ones((px_per_node,px_per_node))),
               vmin=-W_max,vmax=W_max,
               extent=[0,1,0,1],
               interpolation='nearest')
    plt.colorbar()
    plt.title('True Network')
    plt.subplot(1,2,2)

    plt.imshow(np.kron(W_inf,np.ones((px_per_node,px_per_node))),
               vmin=-W_max,vmax=W_max,
               extent=[0,1,0,1],
               interpolation='nearest')
    plt.colorbar()
    plt.title('Inferred Network')

    f.savefig('conn.pdf')
    
    # Plot the stimulus tuning curve
    for n in np.arange(N):
        f = plt.figure()
        if 'stim_t' in true_state[n].keys() and \
            'stim_x' in true_state[n].keys():
            plt.subplot(1,2,1)
            plt.plot(true_state[n]['stim_x'],'b')
            plt.hold(True)
            plt.plot(opt_state[n]['stim_x'],'--r')
            plt.title('GLM[%d]: Spatial stimulus filter' % n)

            plt.subplot(1,2,2)
            plt.plot(true_state[n]['stim_t'],'b')
            plt.hold(True)
            plt.plot(opt_state[n]['stim_t'],'--r')
            plt.title('GLM[%d]: Temporal stimulus filter' % n)
        elif 'stim' in true_state[n].keys():
            plt.plot(true_state[n]['stim'],'b')
            plt.hold(True)
            plt.plot(opt_state[n]['stim'],'--r')
            plt.title('GLM[%d]: stimulus filter' % n)
        f.savefig('stim_resp_%d.pdf' % n)

    # Plot the impulse responses
    W_true = true_state['net']
    W_opt = opt_state['net']
    f = plt.figure()
    for n_pre in np.arange(N):
        for n_post in np.arange(N):
            plt.subplot(N,N,n_pre*N+n_post + 1)
            plt.plot(W_true[n_pre,n_post]*true_state[n_post]['ir'][n_pre,:],'b')
            plt.hold(True)
            plt.plot(W_opt[n_pre,n_post]*opt_state[n_post]['ir'][n_pre,:],'r')
            #plt.title('Imp Response %d->%d' % (n_pre,n_post))
            plt.xlabel("")
            plt.ylabel("")

    f.savefig('imp_resp.pdf')

    # Infer the firing rates
    f = plt.figure()
    for n in np.arange(N):
        plt.subplot(1,N,n+1)
        plt.plot(true_state[n]['lam'],'b')
        plt.hold(True)
        plt.plot(opt_state[n]['lam'],'r')

        # TODO Plot the spike times
        plt.title('Firing rate %d' % n)
    f.savefig('firing_rate.pdf')


if __name__ == "__main__":
    # Test
    print "Initializing GLM"
    T_start = 0
    T_stop = 10000
    dt = 1
    model = make_model('spatiotemporal_glm', N=2)

    dt_stim = 100
    D_stim = model['bkgd']['D_stim']
    N = model['N']

    glm = NetworkGlm(model)
    x_true = glm.sample()

    # Generate random stimulus
    print "Generating random data"
    stim = np.random.randn(T_stop/dt_stim,D_stim)

    # Initialize the GLMs with the stimulus
    data = {"S": np.zeros((T_stop/dt,N)),
            "N": N,
            "dt": dt,
            "T": np.float(T_stop),
            "stim": stim,
            'dt_stim': dt_stim}
    glm.set_data(data)
    
    # Simulate spikes
    S,X = glm.simulate(x_true, (T_start,T_stop), dt)
    
    # Put the spikes into a data dictionary
    data = {"S": S,
            "X": X,
            "N": N,
            "dt": dt,
            "T": np.float(T_stop),
            "stim": stim,
            'dt_stim': dt_stim}
    glm.set_data(data)

    ll_true = glm.compute_log_p(x_true)
    print "true LL: %f" % ll_true

    # Sample random initial state
    x0 = glm.sample()
    ll0 = glm.compute_log_p(x0)
    print "LL0: %f" % ll0

#    x_opt = map_estimate(glm, x0)
    x_opt = coord_descent(glm, x0)
    ll_opt = glm.compute_log_p(x_opt)
    
    print "LL_opt: %f" % ll_opt

    plot_results(glm, x_true, x_opt)