import base64
import time
import datetime

import tweepy
import os

DEBUG = False
try:
	import RPi.GPIO as GPIO
except ImportError as e:
	DEBUG = True
	print e
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

class CameraFailedException(Exception):
	pass

class TickerTickTooManyError(Exception):
	pass

class Loggable(object):
	@classmethod
	def log(cls, message):
		print "[%s][%s] %s\n" % (datetime.datetime.now(), cls.__name__, message)

	@classmethod
	def log_error(cls, message):
		print "[%s][%s] ERROR: %s\n" % (datetime.datetime.now(), cls.__name__, message)

class PinManager(Loggable):
	MODE_OUT = GPIO.OUT
	MODE_IN = GPIO.IN

	def __init__(self, gpio):
		self.log('initializing')
		self.gpio = gpio
		self.gpio.setmode(self.gpio.BCM)

	def setup_pin(self, pin, mode):
		self.log('setup pin %s, %s' % (pin, mode))
		self.gpio.setup(pin, mode)

	def write_pin(self, pin, value):
		self.log("write_pin('%s', %s)" % (pin, value))
		self.gpio.output(pin, value)
	
	def read_pin(self, pin):
		value = self.gpio.input(pin)
		self.log("Read Pin(%s) = %s" % (pin, value))
		return True if value else False

	def cleanup(self):
		self.log('cleanup')
		self.gpio.cleanup()

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

class CatFeederTwitter(Loggable):
	def __init__(self, camera, tweet_at, debug=False):
		self.camera = camera
		self.debug = debug
		self.tweet_at = tweet_at

		twitter_api_key = os.environ.get('TWITTER_API_KEY')
		twitter_api_secret= os.environ.get('TWITTER_API_SECRET')
		twitter_access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
		twitter_access_token_secret= os.environ.get('TWITTER_ACCESS_TOKEN_SECRET')
		auth = tweepy.OAuthHandler(twitter_api_key, twitter_api_secret)
		auth.set_access_token(twitter_access_token, twitter_access_token_secret)
		self.tweepy = tweepy.API(auth)

	def update_status(self, message, take_picture=False):
		if take_picture:
			try:
				filename = self.camera.capture()
			except CameraFailedException as e:
				filename = None

			if not filename:
				self.log_error("Failed to caputure picture")
				return self.update_status(message, False)

			self.tweepy.update_with_media(filename, status=self.format_message(message))
		else:
			self.tweepy.update_status(status=self.format_message(message))

	def format_message(self, message, debug=False):
		if self.debug == True:
			message = "[DEBUG] %s" % message

		message = "%s @%s" % (message, self.tweet_at)
		return message

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

class CatFeeder(Loggable):
	def __init__(self, motor, ticker, twitter, scheduled_feeds):
		self.motor = motor
		self.twitter = twitter
		self.ticker = ticker
		self.scheduled_feeds = scheduled_feeds

		self.current_feed = None
		self.post_started_to_twitter()

	def post_started_to_twitter(self):
		schedule = ["%s:%s:%s" % (scheduled_feed.hour, scheduled_feed.minute, scheduled_feed.second) for scheduled_feed in self.scheduled_feeds]
		self.twitter.update_status("[%s] Startup! Schedule=%s" % (datetime.datetime.now(), schedule))

	def post_feeding_success_to_twitter(self, scheduled_feed):
		self.twitter.update_status('[%s] Scarf was fed %s units.' % (datetime.datetime.now(), scheduled_feed.duration), True)


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

tweet_at = 'tpsreporting'
sleep_interval = 0.1
motor_pin = 22
camera_flash_pin = 6
ticker_pin = 5

pin_manager = PinManager(GPIO)
motor = CatFeederMotor(motor_pin, pin_manager)
ticker = TickerCounter(ticker_pin, pin_manager)
camera = Camera(camera_flash_pin, pin_manager, "/home/pi/webcam/")
twitter = CatFeederTwitter(camera, tweet_at, DEBUG)

if not DEBUG:
	scheduled_feeds = [
		FeedSchedule(15, 0, 0, 3), # 8 AM PST
		FeedSchedule(1, 0, 0, 3) # 6 PM PST
	]
else:
	now = datetime.datetime.now()
	first_time = now + datetime.timedelta(seconds=2)
	second_time = now + datetime.timedelta(seconds=60)
	scheduled_feeds = [
		FeedSchedule(first_time.hour, first_time.minute, first_time.second, 3), # 8 AM PST
		FeedSchedule(second_time.hour, second_time.minute, second_time.second, 3) # 6 PM PST
	]
	class DebugTickerCounter(TickerCounter):
		def __init__(self, ticker_pin, pin_manager):
			self.pin_manager = pin_manager
			self.ticker_pin = ticker_pin
			self.ticks_remaining = 0
			self.activated = False

			self.frequency = 1
			self.last_tick = None
			self.last_state = False

		def read_state(self):
			now = datetime.datetime.now()
			if self.last_tick is None:
				self.last_tick = now

			if now > self.last_tick + datetime.timedelta(seconds=self.frequency):
				self.last_tick = now
				self.last_state = not self.last_state

			return self.last_state

	ticker = DebugTickerCounter(ticker_pin, pin_manager)

cat_feeder = CatFeeder(motor, ticker, twitter, scheduled_feeds)

try:
	while True:
		cat_feeder.update() 
		time.sleep(sleep_interval)

except KeyboardInterrupt as e:
	pass
finally:
	pin_manager.cleanup()
	motor.cleanup()
	camera.cleanup()



