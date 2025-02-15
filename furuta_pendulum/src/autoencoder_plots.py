import matplotlib.pyplot as plt

import seaborn as sns

from torchdiffeq import odeint as odeint

from .trajectories import *
from .dynamics import *


def print_ae_train(x_hat, x, n, horizon):
    """
    Plots predictions and nominal trajectories during training of the autoencoder model
    """
    fig, ax = plt.subplots(1, 4, figsize=(15, 4), constrained_layout=True, sharex=True)
    list_1 = [r"$q1$", r"$\dot{q1}[rad/s]$", r"$q2$", r"$\dot{q2}[rad/s]$"]
    list_2 = ["a", "b", "c", "d"]
    for i in range(4):
        ax[i].plot(x[n, :horizon, i].detach().cpu(), label="nominal")
        ax[i].plot(x_hat[n, :, i].detach().cpu(), "--", label="autencoder")
        ax[i].set_title(list_1[i], fontsize=10)
        ax[i].set_ylabel(list_1[i])
        ax[i].set_xlabel("time (s)")

    ax[3].legend()
    plt.suptitle(
        "Autoencoder output compared to nominal trajectories (Newtonian coordinates)"
    )
    plt.show()


def print_ae_train_all(t_eval, train_x_hat, x_hat, x, n, horizon):
    """
    Plots predictions and nominal trajectories during training of the autoencoder model
    """
    fig, ax = plt.subplots(1, 4, figsize=(15, 4), constrained_layout=True, sharex=True)
    list_1 = [r"$q1$", r"$\dot{q1}[rad/s]$", r"$q2$", r"$\dot{q2}[rad/s]$"]
    list_2 = ["a", "b", "c", "d"]
    for i in range(4):
        ax[i].plot(
            t_eval.detach().cpu(), x[n, :horizon, i].detach().cpu(), label="nominal"
        )
        ax[i].plot(
            t_eval.detach().cpu(), x_hat[n, :, i].detach().cpu(), "--", label="autencoder"
        )
        ax[i].plot(
            t_eval.detach().cpu(),
            train_x_hat[:, n, i].detach().cpu(),
            "--",
            label="HNN_decoded",
        )
        ax[i].set_title(list_1[i], fontsize=10)
        ax[i].set_ylabel(list_1[i])
        ax[i].set_xlabel("time (s)")

    ax[3].legend()
    plt.suptitle(
        "Autoencoder output compared to nominal and predicted(HNN) trajectories (Newtonian coordinates)"
    )
    plt.show()


def plot_distribution(train_loader, save=False, path=""):
    """
    Plot distributions of the trajectories
    """
    x, y = next(iter(train_loader))

    print("Standard deviation of each coordinate: ", (1 / x.std(dim=(0, 1))) * 10)

    fig, ax = plt.subplots(
        1, 4, figsize=(15, 4), constrained_layout=True, sharex=False
    )
    bin = [100, 100, 30, 100]
    titles = [r"$q_1$", r"$\dot{q_1}$", r"$q_2$", r"$\dot{q_2}$"]

    for i in range(4):
       
        sns.histplot(data=x[:, :, i].ravel().detach().cpu(), kde=True, ax=ax[i])

        ax[i].set_ylabel("count")
        ax[i].set_xlabel("value")
        ax[i].set_title(titles[i])

    if save:
        plt.savefig(path, format="png", dpi=400)

    plt.show()


def plot_furuta_ae_twoplots(
    model,
    autoencoder,
    data_loader_tt,
    max_timestep,
    n,
    train_steps,
    time_steps,
    device,
    Ts,
    C_q1,
    C_q2,
    g,
    Jr,
    Lr,
    Mp,
    Lp,
    title="Trajectory of the generalized coordinates",  # , coord_type='hamiltonian'
    file_path=None,
):
    """
    Description:
      This function plots the generalised variables q p, and the energy at the time
      t_eval at which they were evaluated
    Inputs:
        - model (nn.Module) : model that has been trained
        - autoencoder (nn.module) : autoencoder model
        - data_loader_tt (dataloader object) : dataloader that will be used for the 
                                               nominal trajectories
        - max_timestep (int) : time step at which the plot should stop
        - n (int) : integer indicater which sample in the batch from data_loader_tt should
                    be plotted
        - train_steps (int) : how many samples were used in training, these will be shown in
                                green in the plot 
        - time_steps (int) : number of desired time steps
                        (simulate the furta for a number time_steps of time steps)
        - device (string) : device to use to generate the trajectories 
                    (cpu or GPU, use get_device() )
        - Ts (Float) : sampling time
        - C_q1 (Float) : friction coefficient
        - C_q2 (Float) : friction coefficient
        - g, Jr, Lr, Mp, Lp (Float) : furuta pendulum parameters
        - title (string): title of the plot
        - file_path (string) : where to save the plot

    Outputs:
      None
    """
    x_nom, t_eval = next(iter(data_loader_tt))
    # predicted trajectory

    t_eval = t_eval[0, :max_timestep]

    # x_nom = x_nom.permute((0,2,1)) # now x is [batch_size,time_steps,(q1,p1,q2,p1)]
    x_nom = x_nom[:, :max_timestep, :]
    # x_hat is the reconstructed nominal trajectory ; q_dot_hat = decoder(encoder(nominaltrajectory))
    # z is nominal trajectory in latent space (encoded nominal trajectory)
    z, x_hat = autoencoder(x_nom[:, :, :])
    # z is [batch_size,time_steps,(q1,p1,q2,p1)]

    # model output in latent space
    train_z_hat = odeint(
        model, z[:, 0, :], t_eval, method="rk4", options=dict(step_size=Ts)
    )
    # train_z_hat is [time_steps, batch_size, (q1,p1,q2,p1)]

    # HNN decoded trajectory
    # decoded output trajectory
    train_x_hat = autoencoder.decoder(train_z_hat[:, :, :])
    # print(train_x_hat.shape) # [800, 100, 4]
    train_x_hat = train_x_hat.detach().permute(1, 0, 2)

    q1_hat_hnn = train_x_hat[n, :, 0]
    p1_hat_hnn = train_x_hat[n, :, 1]
    q2_hat_hnn = train_x_hat[n, :, 2]
    p2_hat_hnn = train_x_hat[n, :, 3]

    E_hat_hnn, _ = get_energy_furuta_newtonian(
        time_steps,
        device,
        Ts,
        q1_hat_hnn,
        p1_hat_hnn,
        q2_hat_hnn,
        p2_hat_hnn,
        C_q1,
        C_q2,
        g,
        Jr,
        Lr,
        Mp,
        Lp,
    )
    H_hat_hnn = furuta_H(
        q1_hat_hnn, p1_hat_hnn, q2_hat_hnn, p2_hat_hnn, g, Jr, Lr, Mp, Lp
    )

    # Autoencoder trajectory
    x_hat = x_hat.detach()

    q1_hat = x_hat[n, :, 0]
    p1_hat = x_hat[n, :, 1]
    q2_hat = x_hat[n, :, 2]
    p2_hat = x_hat[n, :, 3]

    E_hat, _ = get_energy_furuta_newtonian(
        time_steps,
        device,
        Ts,
        q1_hat,
        p1_hat,
        q2_hat,
        p2_hat,
        C_q1,
        C_q2,
        g,
        Jr,
        Lr,
        Mp,
        Lp,
    )
    H_hat = furuta_H(q1_hat, p1_hat, q2_hat, p2_hat, g, Jr, Lr, Mp, Lp)

    # nominal trajectory
    q1_nom = x_nom[n, :, 0]
    p1_nom = x_nom[n, :, 1]
    q2_nom = x_nom[n, :, 2]
    p2_nom = x_nom[n, :, 3]

    E_nom, _ = get_energy_furuta_newtonian(
        time_steps,
        device,
        Ts,
        q1_nom,
        p1_nom,
        q2_nom,
        p2_nom,
        C_q1,
        C_q2,
        g,
        Jr,
        Lr,
        Mp,
        Lp,
    )
    H_nom = furuta_H(q1_nom, p1_nom, q2_nom, p2_nom, g, Jr, Lr, Mp, Lp)

    fig, ax = plt.subplots(2, 3, figsize=(15, 6), constrained_layout=True, sharex=True)

    t_eval = t_eval.cpu()

    for q1, p1, q2, p2, E, H, label in [
        [q1_nom, p1_nom, q2_nom, p2_nom, E_nom, H_nom, "nominal"]
    ]:

        q1 = q1.cpu()
        p1 = p1.cpu()
        q2 = q2.cpu()
        p2 = p2.cpu()
        E = E.cpu()
        H = H.cpu()

        ax[0, 0].plot(t_eval[:train_steps], q1[:train_steps], label="train", c="g")
        ax[0, 0].plot(
            t_eval[train_steps - 1 :], q1[train_steps - 1 :], label=label, c="C0"
        )

        ax[1, 0].plot(t_eval[:train_steps], p1[:train_steps], label="train", c="g")
        ax[1, 0].plot(
            t_eval[train_steps - 1 :], p1[train_steps - 1 :], label=label, c="C0"
        )

        ax[0, 1].plot(t_eval[:train_steps], q2[:train_steps], label="train", c="g")
        ax[0, 1].plot(
            t_eval[train_steps - 1 :], q2[train_steps - 1 :], label=label, c="C0"
        )

        ax[1, 1].plot(t_eval[:train_steps], p2[:train_steps], label="train", c="g")
        ax[1, 1].plot(
            t_eval[train_steps - 1 :], p2[train_steps - 1 :], label=label, c="C0"
        )

        ax[0, 2].plot(t_eval[:train_steps], E[:train_steps], label="train", c="g")
        ax[0, 2].plot(
            t_eval[train_steps - 1 :], E[train_steps - 1 :], label=label, c="C0"
        )

    for q1, p1, q2, p2, E, H, label in [
        [
            q1_hat_hnn,
            p1_hat_hnn,
            q2_hat_hnn,
            p2_hat_hnn,
            E_hat_hnn,
            H_hat_hnn,
            "prediction",
        ]
    ]:
        q1 = q1.cpu()
        p1 = p1.cpu()
        q2 = q2.cpu()
        p2 = p2.cpu()
        E = E.cpu()
        H = H.cpu()

        ax[0, 0].plot(t_eval, q1, label=label, c="r", linewidth=1)
        ax[1, 0].plot(t_eval, p1, label=label, c="r", linewidth=1)
        ax[0, 1].plot(t_eval, q2, label=label, c="r", linewidth=1)
        ax[1, 1].plot(t_eval, p2, label=label, c="r", linewidth=1)
        ax[0, 2].plot(t_eval, E, label=label, c="r", linewidth=1)

    ax[0, 2].legend()

    # add labels and titles on every plot
    ax[0, 0].set_title("generalized position " + r"$q1$", fontsize=10)
    ax[0, 0].set_ylabel(r"$q1[rad]$")

    ax[1, 0].set_title("generalized velocity " + r"$\dot{q1}$", fontsize=10)
    ax[1, 0].set_xlabel("time [s]")
    ax[1, 0].set_ylabel(r"$\dot{q1}[rad/s]$")

    ax[0, 1].set_title("generalized position " + r"$q2$", fontsize=10)
    ax[0, 1].set_ylabel(r"$q2[rad]$")

    ax[1, 1].set_title(
        "generalized velocity " + r"$\dot{q2}$", fontsize=10
    )  
    ax[1, 1].set_xlabel("time [s]")
    ax[1, 1].set_ylabel(r"$\dot{q2}[rad/s]$")

    ax[0, 2].set_title("Energy", fontsize=10)

    ax[0, 2].set_ylabel("E")


    # add larger title on top
    fig.suptitle(title, fontsize=12)
    fig.delaxes(ax[1, 2])
    if file_path is not None:
        plt.savefig(
            file_path + "first" + ".png", format="png", dpi=400
        ) 
    plt.show()

    fig, ax = plt.subplots(
        2, 3, figsize=(15, 6), constrained_layout=True, sharex=True
    ) 
    for q1, p1, q2, p2, E, H, label in [
        [q1_nom, p1_nom, q2_nom, p2_nom, E_nom, H_nom, "nominal"]
    ]:
        q1 = q1.cpu()
        p1 = p1.cpu()
        q2 = q2.cpu()
        p2 = p2.cpu()
        E = E.cpu()
        H = H.cpu()

        ax[0, 0].plot(t_eval, q1, label=label)
        ax[1, 0].plot(t_eval, p1, label=label)
        ax[0, 1].plot(t_eval, q2, label=label)
        ax[1, 1].plot(t_eval, p2, label=label)
        ax[0, 2].plot(t_eval, E, label=label)

    for q1, p1, q2, p2, E, H, label in [
        [q1_hat, p1_hat, q2_hat, p2_hat, E_hat, H_hat, "AE prediction"]
    ]:
        q1 = q1.cpu()
        p1 = p1.cpu()
        q2 = q2.cpu()
        p2 = p2.cpu()
        E = E.cpu()
        H = H.cpu()

        ax[0, 0].plot(t_eval, q1, label=label, linewidth=1)
        ax[1, 0].plot(t_eval, p1, label=label, linewidth=1)
        ax[0, 1].plot(t_eval, q2, label=label, linewidth=1)
        ax[1, 1].plot(t_eval, p2, label=label, linewidth=1)
        ax[0, 2].plot(t_eval, E, label=label, linewidth=1)

    ax[0, 2].legend()

    ax[0, 0].set_title("generalized position " + r"$q1$", fontsize=10)

    ax[0, 0].set_ylabel(r"$q1[rad]$")

    ax[1, 0].set_title("generalized velocity " + r"$\dot{q1}$", fontsize=10)
    ax[1, 0].set_xlabel("time [s]")
    ax[1, 0].set_ylabel(r"$\dot{q1}[rad/s]$")

    ax[0, 1].set_title("generalized position " + r"$q2$", fontsize=10)

    ax[0, 1].set_ylabel(r"$q2[rad]$")

    ax[1, 1].set_title(
        "generalized velocity " + r"$\dot{q2}$", fontsize=10
    ) 
    ax[1, 1].set_xlabel("time [s]")
    ax[1, 1].set_ylabel(r"$\dot{q2}[rad/s]$")

    ax[0, 2].set_title("Energy", fontsize=10)

    ax[0, 2].set_ylabel("E")

    fig.suptitle(title, fontsize=12)
    fig.delaxes(ax[1, 2])

    if file_path is not None:
        plt.savefig(
            file_path + "second" + ".png", format="png", dpi=400
        ) 
    plt.show()
    return
