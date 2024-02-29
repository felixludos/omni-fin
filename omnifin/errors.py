


class ConnectionNotSet(Exception):
	def __init__(self, message="Connection not set"):
		self.message = message
		super().__init__(self.message)



class NoRecordFound(Exception):
	pass









