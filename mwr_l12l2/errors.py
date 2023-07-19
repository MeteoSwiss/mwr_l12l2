class MWRError(Exception):
    """Base exception for MWR"""


###############################
class MWRInputError(MWRError):
    """Base exception for calling of MWR functions"""


class MWRDataError(MWRError):
    """Raised if something with the input data goes wrong"""


class MWRConfigError(MWRError):
    """Raised if something with the configuration file is wrong"""


###############################
class MissingConfig(MWRConfigError):
    """Raised if a mandatory entry of the config file is missing"""


###############################
class MissingDataError(MWRDataError):
    """Raised if some expected data is not present"""
