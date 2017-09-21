import time
import datetime

class TickerTickTooManyError(Exception):
	pass

class TickerIncrementedEvent(Exception):
	def __init__(self, remaining):
		self.ticks_remaining = remaining
		super(TickerIncrementedEvent, self).__init__("Ticks remaining: %s" % remaining)

class Loggable(object):
	def log(self, message):
		print "[%s][%s] %s\n" % (datetime.datetime.now(), self.__class__.__name__, message)

class TickerCounter(Loggable):
	def __init__(self):
		self.activated = False #make this read from pin
		self.ticks_remaining = 0

	def read_state(self):
		return not self.activated #make this read from pin

	def update(self):
		if self.activated:
			if not self.read_state():
				self.on_ticker_deactivated()
		else:
			if self.read_state():
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
	def __init__(self, scheduled_feeds):
		self.scheduled_feeds = scheduled_feeds
		self.current_feed = None
		self.ticker = TickerCounter()

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

	def stop_feeding(self):
		self.current_feed.calculate_next_time()
		self.log("stop feeding. next scheduled: %s" % self.current_feed.next_time)
		self.current_feed = None

now = datetime.datetime.now()

first_time = now + datetime.timedelta(seconds=5)
second_time = now + datetime.timedelta(seconds=30)

schedule = [
	FeedSchedule(first_time.hour, first_time.minute, first_time.second, 3),
	FeedSchedule(second_time.hour, second_time.minute, second_time.second, 3)
]

cat_feeder = CatFeeder(schedule)

while True:
	cat_feeder.update() 
	time.sleep(1)


