'''FSL-MRS test script

Tests for the quantify module.
Utilise the independently constructed MRS fitting challenge data to test against

Copyright Will Clarke, University of Oxford, 2021'''


import os.path as op
import fsl_mrs.utils.mrs_io as mrsio
from fsl_mrs.utils.fitting import fit_FSLModel
import numpy as np

metabfile = op.join(op.dirname(__file__), 'testdata/quantify/Cr_10mM_test_water_scaling_WS.txt')
h2ofile = op.join(op.dirname(__file__), 'testdata/quantify/Cr_10mM_test_water_scaling_nWS.txt')
basisfile = op.join(op.dirname(__file__), 'testdata/quantify/basisset_JMRUI')


def test_quantifyWater():
    basis, names, headerb = mrsio.read_basis(basisfile)
    crIndex = names.index('Cr')
    data = mrsio.read_FID(metabfile)
    dataw = mrsio.read_FID(h2ofile)

    mrs = data.mrs(basis=basis[:, crIndex],
                   names=['Cr'],
                   basis_hdr=headerb[crIndex],
                   ref_data=dataw)
    mrs.check_FID(repair=True)
    mrs.check_Basis(repair=True)

    Fitargs = {'ppmlim': [0.2, 5.2],
               'method': 'MH',
               'baseline_order': -1,
               'metab_groups': [0]}

    res = fit_FSLModel(mrs, **Fitargs)

    tissueFractions = {'GM': 0.6, 'WM': 0.4, 'CSF': 0.0}
    TE = 0.03
    T2dict = {'H2O_GM': 0.110,
              'H2O_WM': 0.080,
              'H2O_CSF': 2.55,
              'METAB': 0.160}

    res.calculateConcScaling(mrs,
                             referenceMetab=['Cr'],
                             waterRefFID=mrs.H2O,
                             tissueFractions=tissueFractions,
                             TE=TE,
                             T2=T2dict,
                             waterReferenceMetab='Cr',
                             wRefMetabProtons=5,
                             reflimits=(2, 5),
                             verbose=False)

    print(res.getConc(scaling='raw'))
    print(res.getConc(scaling='internal'))
    print(res.getConc(scaling='molality'))
    print(res.getConc(scaling='molarity'))

    assert np.allclose(res.getConc(scaling='internal'), 1.0)
    assert np.allclose(res.getConc(scaling='molarity'), 10.59, atol=1E-1)
