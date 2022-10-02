class PaymentResultConverter:
    regex = "(success|failure)"

    def to_python(self, value):
        return str(value)

    def to_url(self, value):
        return str(value)
