# multinet
A python script that uses linux namespaces to take advantage of multiple network interfaces at the same time.
It lets you launch programs on a namespace with access only to the desired network interface, I call that a... SOLONET!

### Initial setup
Use visudo to add the next line to your sudoers file:
```
<your_user> ALL=(ALL) NOPASSWD:<multinet-exec path> 

```
That will let your user to not need sudo for using the multinet-exec, thats used for running the command ip as your own user, keeping the permissions for your desktop environment.

### How to use it
Disclaimer: To create namespaces you need to be root or sudo.

#### Autorun
After the initial setup, the easier way to use multinet is with the '-a' flag: autorun.
```sh
python multinet.py -a <device> <command>
```
That will automatically set up the solonet for the desired device and launch the command on it.
If the solonet already exists it updates the routing data.

#### Manual mode
You can also manually create a solonet without launching a command with:
```sh
python multinet.py
```
This will open an interactive cli for creating and deleting solonets.
There is no need to use this, most of the time you should use autorun. 