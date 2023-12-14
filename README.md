# NestworkStatePredictor(NSP)

Author:

> Mehdi Attar
>
> Tampere University
>
> Finland

**Introduction**

The NetworkStatePredictor component forecasts the grid state for a specified horizon (e.g., 36 hours). The component is developed to be used in SimCES platform.

**Workflow of NSP**

1. NSP receives the [network ](https://simcesplatform.github.io/energy_msg-init-nis-networkbusinfo/)and [customer](https://simcesplatform.github.io/energy_msg-init-cis-customerinfo/) information data.
2. NSP receives [resource forecast](https://simcesplatform.github.io/energy_msg-resourceforecaststate-power/) data.
3. NSP performs backward forward sweep power flow.
4. NSP published the grid state forecast variables (i.e., [voltage](https://simcesplatform.github.io/energy_msg-networkforecaststate-voltage/) and [current](https://simcesplatform.github.io/energy_msg-networkforecaststate-current/)).


**Epoch workflow**

In beginning of the simulation the NSP component will wait for [SimState](https://simcesplatform.github.io/core_msg-simstate/)(running) message, when the message is received component will initialize and send [Status](https://simcesplatform.github.io/core_msg-status/)(Ready) message with epoch number 0. If SimState(stopped) is received component will close down. Other message are ignored at this stage.

After startup component will begin to listen for [epoch](https://simcesplatform.github.io/core_msg-epoch/) messages. It waits until necessary input data including grid related data ([buses](https://simcesplatform.github.io/energy_msg-init-nis-networkbusinfo/), [components](https://simcesplatform.github.io/energy_msg-init-nis-networkcomponentinfo/) and [customer](https://simcesplatform.github.io/energy_msg-init-cis-customerinfo/)) in addition to [resource forecast](https://simcesplatform.github.io/energy_msg-resourceforecaststate-power/) data arrive.

After receiving the necessary input data, the NSP calculates a power flow. The number of iterations in the power flow depends on the desired acuracy defined in the parametrization. Then grid state forecast variables are published. Then the NSP sends a [status](https://simcesplatform.github.io/core_msg-status/) ready message indicating that all the processes for the running epoch is finished and a new epoch can be started.

If at any stage of the execution Status (Error) message is received component will immediately close down


**Implementation details**

* Language and platform

| Programming language | Python 3.11.4          |
| -------------------- | ----------------------- |
| Operating system     | Windows 10 version 22H2 |

**External packages**

The following packages are needed.

| Package          | Version   | Why needed                                                                                | URL                                                                                                   |
| ---------------- | --------- | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Simulation Tools | (Unknown) | "Tools for working with simulation messages and with the RabbitMQ message bus in Python." | [https://github.com/simcesplatform/simulation-tools](https://github.com/simcesplatform/simulation-tools) |
