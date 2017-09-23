import time
import datetime

try:
	import RPi.GPIO as GPIO
except ImportError as e:
	print e
	class GPIO(object):
		OUT = "out"
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
		def cleanup(cls):
			print "%s.cleanup()" % cls.__name__

SLEEP_INTERVAL = 0.1
class Loggable(object):
	@classmethod
	def log(cls, message):
		print "[%s][%s] %s\n" % (datetime.datetime.now(), cls.__name__, message)

class PinManager(Loggable):
	MODE_OUT = GPIO.OUT
	MODE_IN = GPIO.IN

	@classmethod
	def initalize(cls):
		cls.log('initializing')
		GPIO.setmode(GPIO.BCM)

	@classmethod
	def setup_pin(cls, pin, mode):
		cls.log('setup pin %s, %s' % (pin, mode))
		GPIO.setup(pin, mode)

	@classmethod
	def write_pin(cls, pin, value):
		cls.log("write_pin('%s', %s)" % (pin, value))
		GPIO.output(pin, value)
	
	@classmethod
	def read_pin(cls, pin):
		value = GPIO.input(pin)
		print "Read Pin(%s) = %s" % (pin, value)
		return True if value else False

	@classmethod
	def cleanup(cls):
		cls.log('cleanup')
		GPIO.cleanup()

class TickerTickTooManyError(Exception):
	pass

class TickerIncrementedEvent(Exception):
	def __init__(self, remaining):
		self.ticks_remaining = remaining
		super(TickerIncrementedEvent, self).__init__("Ticks remaining: %s" % remaining)

class TickerCounter(Loggable):
	TICKER_PIN = 5

	def __init__(self):
		self.ticks_remaining = 0
		PinManager.setup_pin(self.TICKER_PIN, GPIO.IN)
		self.activated = self.read_state()

	def read_state(self):
		return PinManager.read_pin(self.TICKER_PIN)

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

class FeedSchedule(Loggable):
	def __init__(self, hour, minute, second, duration):
		self.hour = hour
		self.minute = minute
		self.second = second
		self.duration = duration
		self.next_time = None
		self.calculate_next_time()
		self.log('scheduled feed: %s' % self.next_time)

	def set_next(self):
		self.next_time = self.calculate_next_time()

	def calculate_next_time(self):
		now = datetime.datetime.now()
		feed_time = datetime.datetime(now.year, now.month, now.day, 
			self.hour, self.minute, self.second)
		if feed_time <= now:
			tomorrow = datetime.date.today() + datetime.timedelta(days=1)
			feed_time = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, 
			self.hour, self.minute, self.second)

		self.next_time = feed_time

class CatFeeder(Loggable):
	MOTOR_PIN = 22

	def __init__(self, scheduled_feeds):
		self.scheduled_feeds = scheduled_feeds
		self.current_feed = None
		self.ticker = TickerCounter()
		PinManager.setup_pin(self.MOTOR_PIN, GPIO.OUT)

	def update(self):
		if not self.is_feeding:
			for scheduled_feed in self.scheduled_feeds:
				if scheduled_feed.next_time <= datetime.datetime.now():
					self.start_feeding(scheduled_feed)
					break

		if self.is_feeding:
			try:
				self.ticker.update()
			except TickerIncrementedEvent as e:
				if e.ticks_remaining == 0:
					self.stop_feeding()

	@property
	def is_feeding(self):
		return self.current_feed is not None

	def start_feeding(self, scheduled_feed):
		self.log("start feeding: %s" % scheduled_feed.next_time)
		self.current_feed = scheduled_feed
		self.ticker.count_from(scheduled_feed.duration)
		PinManager.write_pin(self.MOTOR_PIN, True)

	def stop_feeding(self):
		self.current_feed.calculate_next_time()
		self.log("stop feeding. next scheduled: %s" % self.current_feed.next_time)
		self.current_feed = None
		PinManager.write_pin(self.MOTOR_PIN, False)

now = datetime.datetime.now()

first_time = now + datetime.timedelta(seconds=2)
second_time = now + datetime.timedelta(seconds=60)

schedule = [
	FeedSchedule(first_time.hour, first_time.minute, first_time.second, 3),
	FeedSchedule(second_time.hour, second_time.minute, second_time.second, 3)
]

PinManager.initalize()
cat_feeder = CatFeeder(schedule)

try:
	while True:
		cat_feeder.update() 
		time.sleep(SLEEP_INTERVAL)
except Exception as e:
	print e
finally:
	PinManager.write_pin(CatFeeder.MOTOR_PIN, False)
	PinManager.cleanup()



