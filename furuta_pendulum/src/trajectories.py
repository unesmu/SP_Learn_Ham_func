import torch

from torchdiffeq import odeint

from .dynamics import *

"""Functions to generate the trajectories"""


def get_trajectory_furuta(
    device,
    init_method,
    num_trajectories,
    u_func=None,
    g_func=None,
    time_steps=20,
    y0=None,
    noise_std=0.0,
    Ts=0.005,
    C_q1=0.0,
    C_q2=0.0,
    g=9.81,
    Jr=5.72 * 1e-5,
    Lr=0.085,
    Mp=0.024,
    Lp=0.129,
):
    """
    Given the parameters, initial position, and inputs generate  trajectories
    of a furuta pendulum 
    Inputs:
         - device (string) : device to use to generate the trajectories 
                            (cpu or GPU, use get_device() )
         - init_method (string) : how to generate the random initial conditions 
                                (see get_init_state()'s docstring)
         - num_trajectories (int) : number of trajectories
         - u_func (class) : class which containes the input function
         - g_func (class) : class which containes the input matrix
         - time_steps (int) : number of desired time steps
                            (simulate the furta for a number time_steps of time steps)
         - y0 (tensor) : manually enter inital conditions
         - noise_std (Float) : add noise to the created trajectories
         - Ts (Float) : sampling time
         - C_q1 (Float) : friction coefficient
         - C_q2 (Float) : friction coefficient
         - g, Jr, Lr, Mp, Lp (Float) : furuta pendulum parameters
    Outputs:
        - q1, .., p2 (tensor) :  tensor containing generalized coordinates at different time steps
        - t_eval (tensor) : time steps at which the coordinates were generated
    """

    # sampling time

    t_eval = (
        torch.linspace(1, time_steps, time_steps, device=device) * Ts
    )  # evaluated times vector
    t_span = [Ts, time_steps * Ts]  # [t_start, t_end]

    # get initial state
    if y0 is None:
        y0 = get_init_state(num_trajectories, init_method)
        y0 = y0.to(device)

    # solve the differential equation using odeint
    q_p = odeint(
        func=lambda t, coords: dynamics_fn_furuta(
            t, coords, C_q1, C_q2, g, Jr, Lr, Mp, Lp, u_func, g_func
        ),
        y0=y0,
        t=t_eval,
        method="rk4",
        options=dict(step_size=Ts),
    )

    q1, p1, q2, p2 = torch.chunk(q_p, 4, dim=-1)

    # add noise
    if noise_std:
        q1 = q1 + torch.randn(q1.shape, device=device) * noise_std
        p1 = p1 + torch.randn(p1.shape, device=device) * noise_std * torch.max(p1)
        q2 = q2 + torch.randn(q2.shape, device=device) * noise_std
        p2 = p2 + torch.randn(p2.shape, device=device) * noise_std * torch.max(p2)

    q1 = q1.squeeze(dim=-1).detach()
    p1 = p1.squeeze(dim=-1).detach()
    q2 = q2.squeeze(dim=-1).detach()
    p2 = p2.squeeze(dim=-1).detach()

    # .detach() because the pytorch computational graph is no longer needed
    # only the value is needed
    # .squeeze() to have a desired dimentionality
    # *torch.max(p) otherwise noise is too big compared to the generalized momentum

    q1, p1, q2, p2 = (
        q1.permute(1, 0),
        p1.permute(1, 0),
        q2.permute(1, 0),
        p2.permute(1, 0),
    )

    return q1, p1, q2, p2, t_eval.detach()


def get_init_state(n, init_method):
    """
      Returns initial states q1,p1,q2,p2 for the Furuta pendulum
      The angular velocities ( /generalized momenmtums) are set to zero
    Inputs :
      - n (int) : number of initial states
      - init_method (string): The way to generate the random initial states, can be one of: 
            random_nozero
            random_closetozero
            random_closetopi
            random_nozero_pos
            random_closetopi_pos

    Outputs :
      - y0(tensor) : inital conditions

    """

    y0 = torch.zeros(n, 4)

    if init_method == "random_nozero":
        x = torch.ones(n)
        mask = torch.full((n,), fill_value=0.5).bernoulli().bool()
        x[mask] = torch.zeros(len(x[mask])).uniform_(0.3, 2)
        x[~mask] = torch.zeros(len(x[~mask])).uniform_(-2, -0.3)
    elif init_method == "random_closetozero":
        x = torch.zeros(n).uniform_(-0.3, 0.3)
    elif init_method == "random_closetopi":
        x = torch.zeros(n).uniform_(torch.pi - 0.3, torch.pi + 0.3)
    elif init_method == "random_nozero_pos":
        x = torch.zeros(y0.shape[0]).uniform_(0.3, 2)
    elif init_method == "random_closetopi_pos":
        x = torch.zeros(n).uniform_(torch.positive, torch.pi + 0.3)

    y0[:, 0] = x

    # random_uniform_two_interval() centered around pi
    y0[:, 2] = torch.zeros(n).uniform_(torch.pi - 1, torch.pi + 1)

    y0[:, 1] = torch.zeros(n)  # p1 = 0
    y0[:, 3] = torch.zeros(n)  # p2 = 0

    return y0


""" ENERGY functions """


def coord_derivatives_furuta_energy(
    t, coords, C_q1, C_q2, g, Jr, Lr, Mp, Lp, u_func, g_func
):
    """
    Description:
        Returns the derivatives of the generalized coordinates

    Inputs :
      - coords (tensor) : vector containing generalized coordinates q1,p1,q2,p2
      - C_q1 (float) : coefficient of friction related to p1 ( and q1)
      - C_q2 (float) : coefficient of friction related to p2 ( and q2)
      - u_func (class) : class which containes the input function
      - g_func (class) : class which containes the input matrix
      - g, Jr, Lr, Mp, Lp (Float) : furuta pendulum parameters
    Outputs :
      - dq1dt, dp1dt, dq2dt, dp2dt (tensors) : Derivatives w.r.t coords
    """
    if (
        coords.requires_grad is not True
    ):  # coords shape: [timesteps, batchnum, (q1,p1,q2,p2)]
        coords.requires_grad = True

    # Hamiltonian function
    H = hamiltonian_fn_furuta(coords, g, Jr, Lr, Mp, Lp)

    # gradient of the hamiltornian function wrt the generalized coordinates
    dcoords = torch.autograd.grad(H.sum(), coords, create_graph=True)

    dHdq1, dHdp1, dHdq2, dHdp2 = torch.chunk(dcoords[0], 4, dim=-1)

    U = u_func.forward(t)
    G = g_func.forward(coords)
    if not G.shape[0] == 1:
        G = G[0, :].unsqueeze(dim=0)

    U_G = (U.unsqueeze(dim=-1) * G).unsqueeze(dim=-1)

    dq1dt = dHdp1 + (U_G[:, 0])
    dp1dt = -dHdq1 - C_q1 * dHdp1 + (U_G[:, 1])
    dq2dt = dHdp2 + (U_G[:, 2])
    dp2dt = -dHdq2 - C_q2 * dHdp2 + (U_G[:, 3])

    dq1dt, dp1dt, dq2dt, dp2dt = (
        dq1dt.squeeze(dim=-1),
        dp1dt.squeeze(dim=-1),
        dq2dt.squeeze(dim=-1),
        dp2dt.squeeze(dim=-1),
    )
    return dq1dt, dp1dt, dq2dt, dp2dt


def energy_furuta(dq1dt, dq2dt, q1, g, Jr, Lr, Mp, Lp):
    """
    Description:
        Calculate the energy at every time step (dimension two of q1)
    Inputs:
        - q1 (tensor) :  generalized coordinates q1
        - dq1dt, dq2dt (tensor) : derivatives of generalized coordinates
        - g, Jr, Lr, Mp, Lp (Float) : furuta pendulum parameters
    Outputs:
        - E (tensor) : energy evaluated at each time step
    """
    # system constants
    Jp = (1 / 12) * Mp * Lp**2

    # function constants
    C1 = Jr + Mp * Lr**2
    C2 = (1 / 4) * Mp * Lp**2
    C3 = (-1 / 2) * Mp * Lp * Lr
    C4 = Jp + C2
    C5 = (1 / 2) * Mp * g * Lp

    E = (1 / 2) * dq2dt**2 * (
        C1 + C2 * torch.sin(q1) ** 2
    ) + dq2dt * dq1dt * C3 * torch.cos(q1)

    E = E + (1 / 2) * dq1dt**2 * C4 + C5 * torch.cos(q1) + C5

    return E


def get_energy_furuta(
    device,
    time_steps,
    Ts,
    u_func,
    g_func,
    q1,
    p1,
    q2,
    p2,
    C_q1,
    C_q2,
    g,
    Jr,
    Lr,
    Mp,
    Lp,
    time_=None,
):
    """
    Description:
        Wrapper for energy_furuta() which first gets the derivative then calculates the energy
    Inputs:
        - time_steps (int) : number of desired time steps
                            (simulate the furta for a number time_steps of time steps)
        - Ts (Float) : sampling time
        - u_func (class) : class which containes the input function
        - g_func (class) : class which containes the input matrix
        - q1, .., p2 (tensor) :  tensor containing generalized coordinates at different time steps
        - C_q1 (float) : coefficient of friction related to p1 ( and q1)
        - C_q2 (float) : coefficient of friction related to p2 ( and q2)
        - g, Jr, Lr, Mp, Lp (Float) : furuta pendulum parameters
        - time_ (tensor) : (optional) time steps at which coordinates where estimated 
    Outputs:
        - energy (tensor) : energy evaluated at each time step
        - derivatives (tensor) : derivatives evaluated at each time step

    """
    energy = []
    derivatives = []
    if time_ is None:
        time_ = torch.linspace(1, time_steps, time_steps, device=device) * Ts

    coords = torch.stack((q1, p1, q2, p2), dim=-1)

    dq1dt, dp1dt, dq2dt, dp2dt = coord_derivatives_furuta_energy(
        time_, coords, C_q1, C_q2, g, Jr, Lr, Mp, Lp, u_func, g_func
    )

    energy = energy_furuta(dq1dt, dq2dt, q1, g, Jr, Lr, Mp, Lp)

    derivatives = torch.stack((dq1dt, dp1dt, dq2dt, dp2dt), dim=-1)
    return energy, derivatives


def get_energy_furuta_newtonian(
    time_steps, device, Ts, q1, dq1dt, q2, dq2dt, C_q1, C_q2, g, Jr, Lr, Mp, Lp
):
    """
    Description:
        Same as get_energy_furuta() but uses trajectories in the "newtonian"
        space where instead of p1 p2 we have dq1dt and dq1dt

    """

    energy = []
    derivatives = []
    t = torch.linspace(1, time_steps, time_steps, device=device) * Ts

    energy = energy_furuta(dq1dt, dq2dt, q1, g, Jr, Lr, Mp, Lp)

    return energy, derivatives


""" MULTIPLE TRAJECTORIES """


def multiple_trajectories_furuta(
    device,
    init_method,
    time_steps,
    num_trajectories,
    u_func=None,
    g_func=None,
    y0=torch.tensor([1.0, 0.0, 1.0, 0.0]),
    Ts=0.005,
    noise_std=0.0,
    C_q1=0.0,
    C_q2=0.0,
    g=9.81,
    Jr=5.72 * 1e-5,
    Lr=0.085,
    Mp=0.024,
    Lp=0.129,
    energ_deriv=True,
):
    """
    Description:
        Wrapper function for get_trajectory_furuta() and get_energy_furuta() to get the trajectories
        energies, and derivatives.
        See their respective docstrings

    """
    # the first trajectory
    q1, p1, q2, p2, t_eval = get_trajectory_furuta(
        device,
        init_method,
        num_trajectories,
        u_func,
        g_func,
        time_steps,
        y0,
        noise_std,
        Ts,
        C_q1,
        C_q2,
        g,
        Jr,
        Lr,
        Mp,
        Lp,
    )
    energy = []
    derivatives = []

    if energ_deriv:
        energy, derivatives = get_energy_furuta(
            device,
            time_steps,
            Ts,
            u_func,
            g_func,
            q1,
            p1,
            q2,
            p2,
            C_q1,
            C_q2,
            g,
            Jr,
            Lr,
            Mp,
            Lp,
        )

    return q1, p1, q2, p2, energy, derivatives, t_eval
