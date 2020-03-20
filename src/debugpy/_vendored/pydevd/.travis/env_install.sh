# Setup for PyPy and versions pre 3.8 (for 3.8 we use the travis image).
if [[ ("$PYDEVD_USE_CONDA" != "NO") ]]; then

    export CONDA_URL=http://repo.continuum.io/miniconda/Miniconda-latest-Linux-x86_64.sh
    if [ "$TRAVIS_OS_NAME" == "osx" ]; then
        export CONDA_URL=https://repo.continuum.io/miniconda/Miniconda3-latest-MacOSX-x86_64.sh
    fi


    wget $CONDA_URL -O miniconda.sh;
    chmod +x miniconda.sh
    ./miniconda.sh -b
    export PATH=/home/travis/miniconda2/bin:$PATH
    export PATH=/home/travis/miniconda3/bin:$PATH
    export PATH=/Users/travis/miniconda2/bin:$PATH
    export PATH=/Users/travis/miniconda3/bin:$PATH
    conda update --yes conda
fi


# Jython setup
if [ "$PYDEVD_TEST_VM" == "JYTHON" ]; then
    export JYTHON_URL=http://search.maven.org/remotecontent?filepath=org/python/jython-installer/2.7.1/jython-installer-2.7.1.jar
    wget $JYTHON_URL -O jython_installer.jar; java -jar jython_installer.jar -s -d $HOME/jython
    export PATH=$HOME/jython:$HOME/jython/bin:$PATH
    jython -c "print('')"
fi
