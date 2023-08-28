class MWRError(Exception):
    """Base exception for MWR"""


###############################
class MWRFileError(MWRError):
    """Base exception for problems with files used in mwr_l12l2"""


class MWRInputError(MWRError):
    """Base exception for calling of MWR functions"""


class MWRDataError(MWRError):
    """Raised if something with the input data goes wrong"""


class MWRConfigError(MWRError):
    """Raised if something with the configuration file is wrong"""


class MWRTestError(MWRError):
    """Raised if something goes wrong during set up or clean up of testing"""


###############################
class MissingConfig(MWRConfigError):
    """Raised if a mandatory entry of the config file is missing"""


###############################
class MissingDataError(MWRDataError):
    """Raised if some expected data is not present"""


###############################
class FilenameError(MWRFileError):
    """Raised if the filename does not correspond to the expected pattern"""
