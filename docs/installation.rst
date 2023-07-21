Installation
============

Install external dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To run correctly *mwr_l12l2* needs some external dependencies which cannot be installed through *pip*:

#. *TROPoe*: The containerised application for physical radiative transfer inversion retrievals based on MonoRTM
	* https://hub.docker.com/r/davidturner53/tropoe
#. *podman*: A tool to manage and run containers and container images
	* https://podman.io/
#. for grib format usage (e.g. from ECMWF) install the following through your package manager (*apt*, *dnf*, *brew*, ...)
	* *libeccodes0*
	* *libeccodes-tools*
#. for obtaining ECMWF data
	* *mars*: command line utility to obtain ECMWF data
		* https://confluence.ecmwf.int/display/UDOC/MARS+user+documentation


Install mwr_l12l2
^^^^^^^^^^^^^^^^^
*mwr_l12l2* with all its internal depedencies can be installed by *pip*, *poetry* or any other tools which understand
dependency specifications in pyptroject.toml.

from *pypi*
-----------
The package will be released on pypi once it has been thoruoghly tested and quality controlled.
Until then, install from *git*

..
    UNCOMMENT THE FOLLOWING LINES (REMOVING THE ABOVE ".." AND THE FOLLOWING INDENTS) ONCE THE PACKAGE IS ON PYPI
    =============================================================================================================

    *mwr_l12l2* is directly installable through *pip*. To install the latest released version and its dependencies do

    .. code-block::

        pip install mwr_l12l2

    for more colorful logging you may want to do

    .. code-block::

        pip install mwr_l12l2[colorlog]


from *git*
----------
To install *mwr_l12l2* with it's newest developments perform an installation from the source code like follows

1. clone this repository

.. code-block::

    git clone https://github.com/MeteoSwiss/mwr_l12l2.git

2. go into the package directory and install

    - with *pip* (>=21.3)


      .. code-block::

          pip install .

      or

      .. code-block::

          pip install .[colorlog]

    - with *poetry*

      .. code-block::

          poetry install

      or

      .. code-block::

          poetry install -E colorlog
