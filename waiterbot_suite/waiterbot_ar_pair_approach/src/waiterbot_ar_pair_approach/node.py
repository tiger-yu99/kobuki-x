#
# License: BSD
#   https://raw.github.com/robotics-in-concert/rocon_concert/license/LICENSE
#
##############################################################################
# Imports
##############################################################################

import rospy
import std_msgs.msg as std_msgs
import threading
import tf

# Local imports
from .rotate import Rotate

##############################################################################
# Role Manager
##############################################################################


class Node(object):
    '''
      Manages connectivity information provided by services and provides this
      for human interactive agent (aka remocon) connections.
    '''
    __slots__ = [
#            'role_and_app_table',  # Dictionary of string : concert_msgs.RemoconApp[]
            '_publishers',
            '_subscribers',
            '_parameters',
            '_spotted_markers',
            '_thread',
            '_rotate',
            '_rate',
            '_listener',
            '_running'
        ]
    SPOTTED_NONE = 'none'
    SPOTTED_LEFT = 'left'
    SPOTTED_RIGHT = 'right'
    SPOTTED_BOTH = 'both'

    ##########################################################################
    # Initialisation
    ##########################################################################

    def __init__(self):
        self._publishers, self._subscribers = self._setup_ros_api()
        self._parameters = self._setup_parameters()
        self._spotted_markers = Node.SPOTTED_NONE
        self._rotate = Rotate('~cmd_vel')
        self._thread = None
        self._running = False
        self._rate = 0.36  # this could be parameterised
        self._listener = tf.TransformListener()

    def _setup_parameters(self):
        param = {}
        #param['yaw_absolute_rate'] = rospy.get_param('~yaw_absolute_rate', 1.2)
        #param['yaw_update_increment'] = rospy.get_param('~yaw_update_increment', 1.2)
        return param

    def _setup_ros_api(self):
        '''
          These are all public topics. Typically that will drop them into the /concert
          namespace.
        '''
        publishers = {}
        publishers['result'] = rospy.Publisher('~result', std_msgs.Bool)
        subscribers = {}
        subscribers['enable'] = rospy.Subscriber('~enable', std_msgs.Bool, self._ros_enable_subscriber)
        subscribers['spotted_markers'] = rospy.Subscriber('~spotted_markers', std_msgs.String, self._ros_spotted_subscriber)
        return (publishers, subscribers)

    def is_running(self):
        return self._running

    ##########################################################################
    # Ros Api Functions
    ##########################################################################

    def _ros_enable_subscriber(self, msg):
        if msg.data:
            if not self.is_running():
                self._running = True
                self._thread = threading.Thread(target=self.execute)
                self._thread.start()
        else:
            if self._is_running():
                self._publishers['result'].publish(std_msgs.Bool(False))
            self._stop()
            if self._thread is not None:
                self._thread.join()
                self._thread = None

    def _ros_spotted_subscriber(self, msg):
        self._spotted_markers = msg.data
        if self._spotted_markers == Node.SPOTTED_BOTH and self._rotate.is_running():
            self._rotate.stop()
            self._thread.join()
            self._publishers['result'].publish(std_msgs.Bool(True))

    ##########################################################################
    # Execute
    ##########################################################################

    def _stop(self):
        self._rotate.stop()

    def execute(self):
        self._initialise_rotation()
        self._rotate.execute()
        self._running = False

    ##########################################################################
    # Runtime
    ##########################################################################

    def _initialise_rotation(self):
        '''
          Do not call this if already running, you will cause self._rotate to become volatile.
        '''
        direction = Rotate.CLOCKWISE
        if self._spotted_markers == Node.SPOTTED_BOTH:
            rospy.loginfo("AR Pair Search: received an enable command, both spotted markers already in view!")
            self._publishers['result'].publish(std_msgs.Bool(True))
            return
        elif self._spotted_markers == Node.SPOTTED_LEFT:
            rospy.loginfo("AR Pair Search: received an enable command, only left in view.")
        elif self._spotted_markers == Node.SPOTTED_RIGHT:
            rospy.loginfo("AR Pair Search: received an enable command, only right in view.")
            direction = Rotate.COUNTER_CLOCKWISE
        else:  # self._spotted_markers == Node.SPOTTED_NONE
            try:
                # this is from global to base footprint
                (unused_t, orientation) = self._listener.lookupTransform('ar_global', 'base_footprint', rospy.Time(0))
                unused_roll, unused_pitch, yaw = tf.transformations.euler_from_quaternion(orientation)
                rospy.loginfo("AR Pair Search : current yaw = %s" % str(yaw))
                direction = Rotate.COUNTER_CLOCKWISE if yaw > 0 else Rotate.CLOCKWISE
            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException) as unused_e:
                direction = Rotate.COUNTER_CLOCKWISE
            rospy.loginfo("AR Pair Search: received an enable command, none in view.")
        self._rotate.init(yaw_absolute_rate=self._rate, yaw_direction=direction)

    def spin(self):
        '''
          Parse the set of /remocons/<name>_<uuid> connections.
        '''
        rospy.spin()
        if self._thread is not None:
            self._thread.join()
