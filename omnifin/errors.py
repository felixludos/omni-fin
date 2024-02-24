


class ConnectionNotSet(Exception):
	def __init__(self, message="Connection not set"):
		self.message = message
		super().__init__(self.message)



class NoRecordFound(Exception):
	def __init__(self, query=None, message="No record found"):
		if query is not None:
			message = f"No record found for query: {query}"
		self.message = message
		super().__init__(self.message)










