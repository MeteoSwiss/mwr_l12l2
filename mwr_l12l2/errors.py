class MWRError(Exception):
    """Base exception for MWR"""


###############################
class MWRConfigError(MWRError):
    """Raised if something with the configuration file is wrong"""


###############################
class MissingConfig(MWRConfigError):
    """Raised if a mandatory entry of the config file is missing"""