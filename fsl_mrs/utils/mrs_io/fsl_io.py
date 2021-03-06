# fsl_io.py - I/O utilities for fsl_mrs file formats in FSL_MRS
#
# Author: Saad Jbabdi <saad@fmrib.ox.ac.uk>
#         Will Clarke <william.clarke@ndcn.ox.ac.uk>
#
# Copyright (C) 2020 University of Oxford
# SHBASECOPYRIGHT

import numpy as np
import json
import nibabel as nib
import os
import glob
import re
import scipy.signal as ss
from fsl_mrs.core.nifti_mrs import gen_new_nifti_mrs


# NIFTI I/O
def readNIFTI(datafile):
    """ Read old (pre NIFTI-MRS) nifti format file.

    :param str datafile: Path to file
    :return: NIFTI-MRS
    """
    data_hdr = nib.load(datafile)
    data = np.asanyarray(data_hdr.dataobj)
    # look for json sidecar file
    jsonParams = readJSONSidecar(datafile)
    # Sort out header - must contain mandatory fields. Add a nifti header which is unfortunately quite
    # heavy weight as it is the whole loaded object. Add a json header as a nested dict if there is
    # a sidecar file.
    # Reciever bandwidth and dwelltime can either be fetched from the nifti header or the json
    # central frequency is currently only sotred in the json.
    if jsonParams is None:
        raise Exception('Unable to load files without JSON sidecar')
    else:
        if 'Dwelltime' in jsonParams:
            dwelltime = jsonParams['Dwelltime']
        else:
            dwelltime = data_hdr.header['pixdim'][4]
        spec_freq = jsonParams['ImagingFrequency']

        if 'ResonantNucleus' in jsonParams:
            nucleus = jsonParams['ResonantNucleus']
        else:
            nucleus = '1H'

    return gen_new_nifti_mrs(data, dwelltime, spec_freq, nucleus=nucleus, affine=data_hdr.affine)


def saveNIFTI(filepath, data, header, affine=None):
    '''Provide translation layer from old interface to new NIFTI_MRS'''

    gen_new_nifti_mrs(data,
                      1 / header['bandwidth'],
                      header['centralFrequency'],
                      nucleus=header['ResonantNucleus'],
                      affine=affine).save(filepath)


# JSON sidecar I/O
def readJSONSidecar(niftiFile):
    # Determine if there is a json file
    rePattern = re.compile(r'\.nii(\.gz)?')
    jsonFile = rePattern.sub('.json', niftiFile)
    if os.path.isfile(jsonFile):
        return readJSON(jsonFile)
    else:
        return None


def writeJSONSidecar(niftiFile, paramDict):
    rePattern = re.compile(r'\.nii(\.gz)?')
    jsonFile = rePattern.sub('.json', niftiFile)
    writeJSON(jsonFile, paramDict)


def readJSON(file):
    with open(file, 'r') as jsonFile:
        jsonString = jsonFile.read()
    return json.loads(jsonString)


def writeJSON(fileOut, outputDict):
    with open(fileOut, 'w', encoding='utf-8') as f:
        json.dump(outputDict, f, ensure_ascii=False, indent='\t')


# Read a folder containing json files in the FSL basis style.
# Optionally allows recalculation of the FID using the stored density matrix.
# This will take longer but avoids the need for interpolation.
# It also allows for arbitrary shifting of the readout central frequency
def readFSLBasisFiles(basisFolder, readoutShift=4.65, bandwidth=None, points=None):
    if not os.path.isdir(basisFolder):
        raise ValueError(' ''basisFolder'' must be a folder containing basis json files.')
    # loop through all files in folder
    basisfiles = sorted(glob.glob(os.path.join(basisFolder, '*.json')))
    basis, names, header = [], [], []
    for bfile in basisfiles:
        if bandwidth is None or points is None:
            # If simple read operation call readFSLBasis
            b, n, h  = readFSLBasis(bfile)
            basis.append(b)
            names.append(n)
            header.append(h)
        else:
            # If recalculation requested loop through files calling readAndGenFSLBasis
            b, n, h  = readAndGenFSLBasis(bfile, readoutShift, bandwidth, points)
            basis.append(b)
            names.append(n)
            header.append(h)

    basis = np.array(basis).conj().T
    return basis, names, header


# Read the FID within the FSL basis json file. Returns equivalent outputs to the LCModel style basis files.
def readFSLBasis(filename, N=None, dofft=False):
    with open(filename, 'r') as basisFile:
        jsonString = basisFile.read()
        basisFileParams = json.loads(jsonString)
        if 'basis' in basisFileParams:
            basis = basisFileParams['basis']

            data = np.array(basis['basis_re']) + 1j * np.array(basis['basis_im'])

            if dofft:  # Go to frequency domain from timedomain
                data = np.fft.fftshift(np.fft.fft(data))

            # Resample if necessary? --> should not be allowed actually
            if N is not None:
                if N != data.shape[0]:
                    data = ss.resample(data, N)

            header = {'centralFrequency': basis['basis_centre'] * 1E6,
                      'bandwidth': 1 / basis['basis_dwell'],
                      'dwelltime': basis['basis_dwell'],
                      'fwhm': basis['basis_width']}
            # header['echotime'] Not clear how to calculate this in the general case.

            metabo = basis['basis_name']

        else:  # No basis information found
            raise ValueError('FSL basis file must have a ''basis'' field.')

    return data, metabo, header


# Load an FSL basis file.
# Recalculate the FID on a defined time axis.
# Relies on all fields being populated appropriately
def readAndGenFSLBasis(file, readoutShift, bandwidth, points):
    from fsl_mrs.denmatsim import utils as simutils
    with open(file, 'r') as basisFile:
        jsonString = basisFile.read()
        basisFileParams = json.loads(jsonString)

    if 'MM' in basisFileParams:
        import fsl_mrs.utils.misc as misc
        FID, metabo, header = readFSLBasis(file)
        old_dt = 1 / header['bandwidth']
        new_dt = 1 / bandwidth
        FID     = misc.ts_to_ts(FID, old_dt, new_dt, points)
        return FID, metabo, header

    if 'seq' not in basisFileParams:
        raise ValueError('To recalculate the basis json must contain a seq field containing a B0 field.')
    else:
        B0 = basisFileParams['seq']['B0']
        if 'Rx_Phase' not in basisFileParams['seq']:
            rxphs = 0
        else:
            rxphs = basisFileParams['seq']['Rx_Phase']

    if 'spinSys' not in basisFileParams:
        raise ValueError('To recalculate the basis json must contain a spinSys field.')
    else:
        spins = basisFileParams['spinSys']

    if 'outputDensityMatrix' not in basisFileParams:
        raise ValueError('To recalculate the basis json must contain a outputDensityMatrix field.')
    else:
        p = []
        for real, imag in zip(basisFileParams['outputDensityMatrix']['re'],
                              basisFileParams['outputDensityMatrix']['im']):
            p.append(np.array(real) + 1j * np.array(imag))
        if len(p) == 1:
            p = p[0]  # deal with single spin system case

    lw = basisFileParams['basis']['basis_width']
    FID = simutils.FIDFromDensityMat(p,
                                     spins,
                                     B0,
                                     points,
                                     1 / bandwidth,
                                     lw,
                                     offset=readoutShift,
                                     recieverPhs=rxphs)

    metabo = basisFileParams['basis']['basis_name']
    cf = basisFileParams['basis']['basis_centre'] * 1E6
    header = {'centralFrequency': cf,
              'bandwidth': bandwidth,
              'dwelltime': 1 / bandwidth,
              'fwhm': lw}

    return FID, metabo, header
