"""Terminal status helpers + floating Command Pill overlay.

CLI prints always run. The CustomTkinter pill is voice-mode only after
``init_command_pill()``. Background threads must NEVER touch Tk widgets —
use ``set_state()`` / the status helpers, which enqueue updates for the GUI
thread's ``after()`` poller.
"""

from tars.ui.pill import *  # noqa: F403
