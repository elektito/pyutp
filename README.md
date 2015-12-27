pyutp
=====

This is a `ctypes` based wrapper around [libutp][1]. You need libutp
shared object available in such a place known to the system dynamic
library loader. Something like this will do the trick on Ubuntu:

    $ git clone https://github.com/bittorrent/libutp
    $ cd libutp
    $ make
    $ sudo install libutp.so /usr/lib/

After this, you can use pyutp almost the same way you can use
libutp. This is currently a very thin Python wrapper around most of
libutp. I'm hoping to make it more complete and more Pythonic soon.

 [1]: https://github.com/bittorrent/libutp
