class ComparisonError(ValueError):
    """Invalid engine input, configuration or model output."""

    def __init__(self, message, *, code=None):
        super().__init__(message)
        self.code = code


class ChatError(ComparisonError):
    pass


class ComparisonNotReadyError(ChatError):
    pass


class ComparisonAlreadyReadyError(ComparisonError):
    pass
