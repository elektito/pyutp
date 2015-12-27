Callbacks
=========

This is a list of the callback functions supported by pyutp. These are
all equivalent to their counterparts in libutp, except that the
arguments are passed individually instead of as a single struct. All
callbacks share the same first two arguments:

 - `cb`: callback type; one of the values that can be passed to
   `utp_set_callback`.
 - `ctx`: the utp context.

The rest of the arguments are specific to each callback and are
described below:

1. `on_firewall(cb, ctx, addr)`

   This callback gives you a chance to choose which inbound
   connections to accept and which not to. A True return value means
   to *block* the request. False means to accept it.

2. `on_accept(cb, ctx, sock, addr)`

   If this callback is set, inbound connections are accepted
   (conditional to the return value of `on_firewall`, which will be
   called before this one, of course). `sock` is a socket for the
   accepted connection. `addr` is a `(host, port)` pair identifying
   the remote peer.

3. `on_connect(cb, ctx, sock)`

   This callback is called when the socket goes to the *CONNECTED*
   state, that is when the connection to the remote peer is
   established. `sock` is the socket for which the connection has been
   established.

4. `on_error(cb, ctx, sock, error_code)`

   This callback is called when an error has occurred in a socket. The
   error is identified by the `error_code` passed. `sock` is the
   socket in which an error has occurred.

5. `on_read(cb, ctx, sock, data)`

   This callback is called when there is incoming data to be
   read. `sock` is the socket from which some data has arrived and
   `data` is what has arrived.

6. `on_overhead_statistics(cb, ctx, sock, send, length, type)

   This callback is called whenever some overhead bandwidth has been
   used by the protocol. `sock` is the connection for which the stats
   are being reported. `send` is a boolean determining whether the
   stats are for a send operation or a receive. `length` is the amount
   of overhead. `type` determines the type of the overhead and is one
   of the following values:

    - `CONNECT_OVERHEAD`: The overhead incurred for establishing the
      connection.
    - `CLOSE_OVERHEAD`: The overhead incurred for closing the
      connection.
    - `ACK_OVERHEAD`: The overhead incurred for sending
      acknowledgments.
    - `HEADER_OVERHEAD`: The overhead incurred for UDP and UTP
      headers.
    - `RETRANSMIT_OVERHEAD`: The overhead incurred for re-transmitting
      lost segments.

7. `on_state_change(cb, ctx, sock, state)`

   This callback is called whenever the state of a socket has
   changed. If the `on_connect` callback is set, this function is
   _not_ called when the socket enters the *CONNECTED* state. `sock`
   is the socket the state of which has changed. `state` is the new
   state of the socket and has one of the following values:

    - `UTP_STATE_CONNECT`: The connection was established.
    - `UTP_STATE_WRITABLE`: The socket is now writable.
    - `UTP_STATE_EOF`: The socket can no longer be written to.
    - `UTP_STATE_DESTROYING`: The socket is being destroyed.

8. `get_read_buffer_size(cb, ctx, sock)`

   Allows you to set the read buffer size for a socket. The callback
   should return the desired value for the read buffer size, which
   must be a positive integer.

9. `on_delay_sample(cb, ctx, sock sample_ms)`

   This callback is called whenever the congestion control algorithm
   is being invoked and informs you of the current delay
   sample. `sock` is the socket for which the sample is being
   reported, and `sample_ms` is the delay sample in milliseconds.

10. `get_udp_mtu(cb, ctx, sock, addr)`

   Gives you a chance to set the UDP maximum transmission unit
   (MTU). `sock` is a UTP socket and `addr` is the `(host, port)` pair
   for which the MTU is being asked.

11. `get_udp_overhead(cb, ctx, sock, addr)`

   Gives you a chance to set the UDP overhead. `sock` is a UTP socket
   for which this is being asked and `addr` a `(host, port)` pair.

12. `get_milliseconds(cb, ctx, sock)`

   Gives you a chance to set the current time. The return value should
   be the number of milliseconds passed since epoch.

12. `get_microseconds(cb, ctx, sock)`

   Gives you a chance to set the current time. The return value should
   be the number of microseconds passed since epoch.

13. `utp_get_random(cb, ctx, sock)`

   Gives you a chance to return a random number for use by libutp. The
   return value should be a random 32-bit integer.

14. `utp_log(cb, ctx, sock, msg)`

   This callback is called whenever there is a log message
   available. `sock` is the socket for which the message is being
   logged, and `msg` is the message being logged.

   The amount of messages being logged depends on the options set by
   calling the `utp_context_set_option` function.

15. `utp_sendto(cb, ctx, sock, data, addr, flags)`

   This callback is called whenever a UDP datagram needs to be
   sent. `sock` is the socket that is transmitting. `data` is the data
   segment being transmitted. `addr` is the address of the remote peer
   as a `(host, port)` pair. `flags` is an integer determining a set
   of transmission flags. At the moment the only flag is
   `UTP_UDP_DONT_FRAG`.
