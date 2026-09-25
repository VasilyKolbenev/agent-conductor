"""Ownership refusal vocabulary; importing it has no machine-facing effects."""


class OwnerRefused(RuntimeError):
    def __init__(self, code, detail):
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}")
