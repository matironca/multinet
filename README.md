# multinet
A python script that uses linux namespaces to take advantage of multiple network interfaces at the same time.

### Initial setup
Use visudo to add the next line to your sudoers file:
```
<your_user> ALL=(ALL) NOPASSWD:<multinet-exec path> 

```
That will let your user to not need sudo for using the multinet-exec, thats used for running the command ip as your own user, keeping the permissions for your desktop environment.



