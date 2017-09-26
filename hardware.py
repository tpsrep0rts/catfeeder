import time
import datetime
from loggable import Loggable

DEBUG = False
try:
	import RPi.GPIO as GPIO
except ImportError as e:
	DEBUG = True
	class GPIO(object):
		OUT = "out"
		IN = "in"
		BCM = "bcm"

		@classmethod
		def setmode(cls, mode):
			print "%s.setmode('%s')" % (cls.__name__, mode)

		@classmethod
		def setup(cls, pin, mode):
			print "%s.setup(%s, '%s')" % (cls.__name__, pin, mode)

		@classmethod
		def output(cls, pin, value):
			print "%s.output('%s', %s)" % (cls.__name__, pin, value)

		@classmethod
		def input(cls, pin):
			return 0

		@classmethod
		def cleanup(cls):
			print "%s.cleanup()" % cls.__name__

class PinManager(Loggable):
	MODE_OUT = GPIO.OUT
	MODE_IN = GPIO.IN

	def __init__(self,):
		self.log('initializing')
		GPIO.setmode(GPIO.BCM)

	def setup_pin(self, pin, mode):
		self.log('setup pin %s, %s' % (pin, mode))
		GPIO.setup(pin, mode)

	def write_pin(self, pin, value):
		self.log("write_pin('%s', %s)" % (pin, value))
		GPIO.output(pin, value)
	
	def read_pin(self, pin):
		value = GPIO.input(pin)
		self.log("Read Pin(%s) = %s" % (pin, value))
		return True if value else False

	def cleanup(self):
		self.log('cleanup')
		GPIO.cleanup()

class CatFeederMotor(Loggable):
	def __init__(self, motor_pin, pin_manager):
		self.motor_pin = motor_pin
		self.pin_manager = pin_manager
		self.pin_manager.setup_pin(self.motor_pin, GPIO.OUT)

	def start_motor(self):
		self.pin_manager.write_pin(self.motor_pin, True)

	def stop_motor(self):
		self.pin_manager.write_pin(self.motor_pin, False)

	def cleanup(self):
		self.pin_manager.write_pin(self.motor_pin, False)

class TickerTickTooManyError(Exception):
	pass

class TickerIncrementedEvent(Exception):
	def __init__(self, remaining):
		self.ticks_remaining = remaining
		super(TickerIncrementedEvent, self).__init__("Ticks remaining: %s" % remaining)

class TickerCounter(Loggable):
	def __init__(self, ticker_pin, pin_manager):
		self.pin_manager = pin_manager
		self.ticker_pin = ticker_pin
		self.ticks_remaining = 0
		self.pin_manager.setup_pin(self.ticker_pin, PinManager.MODE_IN)
		self.activated = self.read_state()

	def read_state(self):
		return self.pin_manager.read_pin(self.ticker_pin)

	def update(self):
		ticker_activated = self.read_state()
		if self.activated:
			if not ticker_activated:
				self.on_ticker_deactivated()
		else:
			if ticker_activated:
				self.on_ticker_activated()

	def on_ticker_activated(self):
		self.activated = True
		self.log("ticker activated")

	def on_ticker_deactivated(self):
		self.activated = False
		self.log("ticker deactivated")
		self.increment_ticker()
		raise TickerIncrementedEvent(self.ticks_remaining) #communicate the tick

	def increment_ticker(self):
		if self.ticks_remaining == 0:
			raise TickerTickTooManyError()

		self.ticks_remaining = self.ticks_remaining - 1
		self.log("Tick! Remaining: %s" % self.ticks_remaining)

	def count_from(self, ticks):
		self.ticks_remaining = ticks

class CameraFailedException(Exception):
	pass

class Camera(Loggable):
	def __init__(self, flash_pin, pin_manager, output_directory):
		self.flash_pin = flash_pin
		self.pin_manager = pin_manager
		self.output_directory = output_directory
		self.pin_manager.setup_pin(self.flash_pin, GPIO.OUT)
		
	def capture(self, use_flash=True):
		if use_flash:
			self.pin_manager.write_pin(self.flash_pin, True)
			self.log("Flash Started")

		self.log("Capture image")
		filename = "%s/%s.jpg" % (self.output_directory, datetime.datetime.now())
		os.system('fswebcam "%s"' % filename)

		if use_flash:
			self.pin_manager.write_pin(self.flash_pin, False)
			self.log("Flash Stopped")

		if not os.path.isfile(filename):
			raise CameraFailedException()

		return filename

	def cleanup(self):
		self.pin_manager.write_pin(self.flash_pin, False)

class CatFeeder(Loggable):
	def __init__(self, motor, ticker, twitter, scheduled_feeds, sleep_interval):
		self.motor = motor
		self.twitter = twitter
		self.ticker = ticker
		self.scheduled_feeds = scheduled_feeds
		self.sleep_interval = sleep_interval

		self.current_feed = None
		self.post_started_to_twitter()

	def post_started_to_twitter(self):
		schedule = ["%s:%s:%s" % (scheduled_feed.hour, scheduled_feed.minute, scheduled_feed.second) for scheduled_feed in self.scheduled_feeds]
		self.twitter.update_status("[%s] Startup! Schedule=%s" % (datetime.datetime.now(), schedule))

	def start(self):
		while True:
			self.update() 
			time.sleep(self.sleep_interval)

	def update(self):
		if not self.is_feeding:
			for scheduled_feed in self.scheduled_feeds:
				if scheduled_feed.next_time <= datetime.datetime.now():
					self.on_start_feeding(scheduled_feed)
					break

		if self.is_feeding:
			try:
				self.ticker.update()
			except TickerIncrementedEvent as e:
				if e.ticks_remaining == 0:
					self.on_stop_feeding()

	@property
	def is_feeding(self):
		return self.current_feed is not None

	def on_start_feeding(self, scheduled_feed):
		self.log("start feeding: %s" % scheduled_feed.next_time)
		self.current_feed = scheduled_feed
		self.ticker.count_from(scheduled_feed.duration)

	def on_stop_feeding(self):
		self.current_feed.calculate_next_time()
		self.log("stop feeding. next scheduled: %s" % self.current_feed.next_time)
		time.sleep(10)
		self.post_feeding_success_to_twitter(self.current_feed)
		self.current_feed = None

	def post_feeding_success_to_twitter(self, scheduled_feed):
		self.twitter.update_status('[%s] Scarf was fed %s units.' % (datetime.datetime.now(), scheduled_feed.duration), True)
