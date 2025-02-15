import time
import torch

from torch.optim.lr_scheduler import LinearLR

from .plots import *
from .dynamics import *
from .trajectories import *
from .utils import *
from .train_helpers import *



def train(
    device,
    model,
    Ts,
    train_loader,
    test_loader,
    w,
    grad_clip,
    lr_schedule,
    begin_decay,
    resnet_config=False,
    alternating=False,
    horizon=False,
    horizon_type=False,
    horizon_list=[50, 100, 150, 200, 250, 300],
    switch_steps=[200, 200, 200, 150, 150, 150],
    epochs=20,
    loss_type="L2",
    collect_grads=False,
    rescale_loss=False,
    rescale_dims=[1, 1, 1, 1],
):
    """
    Description:
        Training function used for all the models on the furuta pendulum, except for
        the (autoencoder+simpleHNN) model
    Inputs:
        - device (string) : device to use to generate the trajectories 
                            (cpu or GPU, use get_device() )
        - model (nn.Module) : model that has been trained 
        - Ts (Float) : sampling time
        - train_loader (data loader object) : train loader 
        - test_loader (data loader object) : test loader 
        - w (bool or tensor) : either false or a tensor containing the weights
                             to rescale each coordinate 
        - grad_clip (bool) : activate gradient clipping or not
        - lr_schedule (bool) : use a learning rate scheduler or not
        - begin_decay (int) : epoch at which learning rate decay should start
        - resnet_config (int) : resnet config, one of the folowing numbers:
                                    - 1 : Expanding HNN (and its variants)
                                    - 2 : Interp HNN (and its variants)
        - alternating (bool) : if true every epoch there are two iterations, one
                               iteration where the NN approximating the Hamiltonian
                               function is frozen, and one epoch where the NN approximating
                               the input matrix is frozen
        - horizon (int or bool) : if a constant training horizon is wanted use this
                          otherwise set to False
        - horizon_type (string) : type of horizon can be :
                                                    - 'auto' : is determined by a function 
                                                               and the training epoch
                                                    - 'constant' : stays constant
        - horizon_list (list) : horizons with which the model will be trained
        - switch_steps (list) : number of epochs per horizon
        - epochs (int) : number of training epochs
        - loss_type (string) : type of loss, can be one of : 'L2weighted' or 'L2'
        - collect_grads (bool) : save the gradient values during training
        - rescale_loss (bool) : rescale the loss function during training
        - rescale_dims (list): list containing how the coordinates were rescaled

    Outptus:
        - logs (dict) : dict containing statistics from the training run
    """

    optim = torch.optim.AdamW(model.parameters(), lr= 1e-3, weight_decay=1e-4)  # Adam
    if lr_schedule:
        scheduler = LinearLR(
            optim, start_factor=1.0, end_factor=0.5, total_iters=epochs - begin_decay
        )

    logs = {
        "train_loss": [],
        "test_loss": [],
        "grads_preclip": [],
        "grads_postclip": [],
        "layer_names": [],
    }

    denom = torch.tensor([1], device=device)
    denom_test = torch.tensor([1], device=device)
    horizon_updated = 1

    for step in range(epochs):

        train_loss = 0
        test_loss = 0
        t1 = time.time()

        if horizon_type == "auto":
            horizon_updated, horizon = select_horizon_list(
                step, epochs, horizon_list, switch_steps
            )
        elif horizon_type == "constant":
            horizon = horizon

        # increase the model size and initialie the new parameters
        if resnet_config:
            model = multilevel_strategy_update(
                device, step, model, resnet_config, switch_steps
            )

        model.train()

        for i_batch, (x, t_eval) in enumerate(train_loader):
            # x is [batch_size, time_steps, (q1,p1,q2,p1,u,g1,g2,g3,g4)]

            t_eval = t_eval[0, :horizon]

            # calculate (max-min) to rescale the loss function
            if rescale_loss:
                if horizon_updated:
                    _, _, denom = get_maxmindenom(
                        x=x[:, :horizon, :4].permute(1, 0, 2),
                        dim1=(0),
                        dim2=(0),
                        rescale_dims=rescale_dims,
                    )

            for i in range(
                2 if alternating else 1
            ):  # only runs once if alternating = False
                if i == 0 and alternating:  # train only the model approximating G
                    model.freeze_H_net(freeze=True)
                    model.freeze_G_net(freeze=False)
                elif i == 1 and alternating:  # train only the model approximating H
                    model.freeze_H_net(freeze=False)
                    model.freeze_G_net(freeze=True)

                train_x_hat = odeint(
                    model, x[:, 0, :4], t_eval, method="rk4", options=dict(step_size=Ts)
                )
                # train_x_hat is [time_steps, batch_size, (q1,p1,q2,p1)]

                train_loss_mini = L2_loss(
                    x[:, :horizon, :4].permute(1, 0, 2),
                    train_x_hat[:, :, :4],
                    w,
                    param=loss_type,
                    rescale_loss=rescale_loss,
                    denom=denom,
                )
                # after permute x is [time_steps, batch_size, (q1,p1,q2,p1)]

                if (not step % 10) and (i_batch == 0):
                    t_plot = time.time()
                    training_plot(t_eval, train_x_hat[:, :, :4], x[:, :horizon, :4])
                    print("plot time :", time.time() - t_plot)

                train_loss = train_loss + train_loss_mini.item()

                train_loss_mini.backward()
                if collect_grads:
                    layer_names, all_grads_preclip = collect_gradients(
                        model.named_parameters()
                    )

                if grad_clip:  # gradient clipping to a norm of 1
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                if collect_grads:
                    layer_names, all_grads_postclip = collect_gradients(
                        model.named_parameters()
                    )
                    logs["layer_names"].append(layer_names)
                    logs["grads_preclip"].append(all_grads_preclip)
                    logs["grads_postclip"].append(all_grads_postclip)

                optim.step()
                optim.zero_grad()

                if step > begin_decay and lr_schedule:
                    scheduler.step()


        t2 = time.time()
        train_time = t2 - t1

        model.eval()
        if test_loader:
            if not (step % 10):  # run validation every 10 steps
                for x, t_eval in iter(test_loader):

                    with torch.no_grad():  # we won't need gradients for testing
                        # run test data
                        t_eval = t_eval[0, :horizon]
                        if rescale_loss:
                            if horizon_updated:
                                _, _, denom_test = get_maxmindenom(
                                    x=x[:, :horizon, :4].permute(1, 0, 2),
                                    dim1=(0),
                                    dim2=(0),
                                    rescale_dims=rescale_dims,
                                )

                        test_x_hat = odeint(
                            model,
                            x[:, 0, :4],
                            t_eval,
                            method="rk4",
                            options=dict(step_size=Ts),
                        )


                        test_loss_mini = L2_loss(
                            x[:, :horizon, :4].permute(1, 0, 2),
                            test_x_hat[:horizon, :, :4],
                            w,
                            param=loss_type,
                            rescale_loss=rescale_loss,
                            denom=denom_test,
                        )
                        test_loss = test_loss + test_loss_mini.item()
                test_time = time.time() - t2
                print(
                    "epoch {:4d} | train time {:.2f} | train loss {:8e} | test loss {:8e} | test time {:.2f}  ".format(
                        step, train_time, train_loss, test_loss, test_time
                    )
                )
                logs["test_loss"].append(test_loss)

            else:
                print(
                    "epoch {:4d} | train time {:.2f} | train loss {:8e} ".format(
                        step, train_time, train_loss
                    )
                )
        else:
            print(
                "epoch {:4d} | train time {:.2f} | train loss {:8e} ".format(
                    step, train_time, train_loss
                )
            )

        # logging
        logs["train_loss"].append(train_loss)
    return logs
