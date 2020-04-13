# quantify.py - Quantify the results of MRS fits
#
# Author: Will Clarke <william.clarke@ndcn.ox.ac.uk>
#         Saad Jbabdi <saad@fmrib.ox.ac.uk>
#
# Copyright (C) 2020 University of Oxford 
# SHBASECOPYRIGHT

from fsl_mrs.utils.constants import H2O_MOLECULAR_MASS, H2O_MOLALITY, TISSUE_WATER_DENSITY,STANDARD_T2,H1_gamma,H2O_PROTONS
import numpy as np
from fsl_mrs.utils.misc import FIDToSpec

def calculate_area(mrs,FID,ppmlim=None):
    """
        Calculate area of the real part of the spectrum between two limits
    """
    Spec = FIDToSpec(FID,axis=0)
    if ppmlim is not None:
        first,last = mrs.ppmlim_to_range(ppmlim)
        Spec = Spec[first:last]
    area = np.trapz(np.real(Spec),axis=0)
    return area

def quantifyInternal(reference,concentrations,names):
    """ Calculate scaling for internal referencing"""
    concSum = 0
    if isinstance(reference,list):
        for m in reference:
            if m not in names:
                raise ValueError(f'Internal reference {m} is not a recognised metabolite.')
            concSum += concentrations[names.index(m)]
    else:
        if reference not in names:
            raise ValueError(f'Internal reference {reference} is not a recognised metabolite.')
        concSum += concentrations[names.index(reference)]

    return 1/concSum

def quantifyWater(mrs,H2OFID,refFID,referenceName,concentrations,metaboliteNames,refProtons,Q,reflimits=None,verbose=False):
    """Calculate scalings required to take raw concentrations to molarity or molality units.

    Steps:
        1) Calculate areas of the peaks in the water reference and of the fitted reference peaks.
        2) Calculate the scalings between the reference peak area and water area
        3) Add in the scalings betweent he reference peak and all other peaks.

    Args:
            mrs (MRS obj): Current MRS object
            H2OFID (np.array): FID of wate reference
            refFID (np.array): FID of fitted reference metabolite
            referenceName (str): Name of reference metabolite
            concentrations (np.array): All metabolite raw concentrations
            metaboliteNames (list:str): All metabolite names           
            refProtons (): Number of protons contributing to reference spectrum between reflimits
            Q (QuantificationInfo object): Contains tissue information
            reflimits (tuple:float): Limits of integration for reference metabolite
            verbose (bool): Verbose output

    Returns:
        conc_molal (float): Scaling parameter to convert raw fitted concnetrations to molality units of mols/kg
        conc_molar (float): Scaling parameter to convert raw fitted concnetrations to molarity units of mols/dm^3
    """
    
    # Calculate observed areas
    SMObs = calculate_area(mrs,refFID,ppmlim=reflimits)
    SH2OObs = calculate_area(mrs,H2OFID,ppmlim=None)

    # Calculate concnetration scalings
    # EQ 4 and 6 in https://doi.org/10.1002/nbm.4257
    conc_molal =  (SMObs *(Q.f_GM*Q.R_H2O_GM + Q.f_WM*Q.R_H2O_WM + Q.f_CSF*Q.R_H2O_CSF)/(SH2OObs*(1-Q.f_CSF)*Q.R_M)) \
                    * (H2O_PROTONS/refProtons)\
                    * H2O_MOLALITY
    
    conc_molar =  (SMObs *(Q.f_GM*Q.d_GM*Q.R_H2O_GM + Q.f_WM*Q.d_WM*Q.R_H2O_WM + Q.f_CSF*Q.d_CSF*Q.R_H2O_CSF)/(SH2OObs*(1-Q.f_CSF)*Q.R_M))\
                    * (H2O_PROTONS/refProtons)\
                    * H2O_MOLALITY

    if verbose:
        rcorwaterconc = (Q.f_GM*Q.d_GM*Q.R_H2O_GM + Q.f_WM*Q.d_WM*Q.R_H2O_WM + Q.f_CSF*Q.d_CSF*Q.R_H2O_CSF)*H2O_MOLALITY
        metabRelaxCorr = 1/Q.R_M
        print(f'Metabolite area = {SMObs:0.2e}')
        print(f'Water area = {SH2OObs:0.2e}') 
        print(f'Relaxation corrected water concentration = {rcorwaterconc:0.2e}')
        print(f'metabolite relaxation correction  = {metabRelaxCorr:0.2e}')
        print(f'H2O to ref molality scaling = {conc_molal:0.2e}') 
        print(f'H2O to ref molarity scaling = {conc_molar:0.2e}')  

    # Calculate other metabolites to reference scaling 
    metabtoRefScaling = quantifyInternal(referenceName,concentrations,metaboliteNames)
    conc_molal *= metabtoRefScaling
    conc_molar *= metabtoRefScaling

    if verbose:
        print(f'Ref to other metabolite scaling = {metabtoRefScaling:0.2e}') 
        print(f'Final molality scaling = {conc_molal:0.2e}') 
        print(f'Final molarity scaling = {conc_molar:0.2e}')

    return conc_molal,conc_molar

class QuantificationInfo(object):
    """ Class encapsulating the information required to run internal water quantification scaling."""
    def __init__(self,TE,T2,tissueFractions,tissueDensity=None):
        """Constructor for QuantificationInfo. Requires sequence and tissue information.

        Args:
            TE (float): Sequence echo time in seconds
            T2 (dict:float): Tissue T2 values. Must contain 'H2O_GM', 'H2O_WM','H2O_CSF' and 'METAB' fields. In seconds.
            tissueFractions (dict:float): Tissue volume fractions, must contain 'WM', 'GM', 'CSF' fields.
            tissueDensity (dict:float, optional): Tissue volume fractions, must contain 'WM', 'GM', 'CSF' fields. In units of g/ml.
        """

        if tissueDensity is None:
            self.d_GM  = TISSUE_WATER_DENSITY['GM']
            self.d_WM  = TISSUE_WATER_DENSITY['WM']
            self.d_CSF = TISSUE_WATER_DENSITY['CSF']
        else:
            self.d_GM  = tissueDensity['GM']
            self.d_WM  = tissueDensity['WM']
            self.d_CSF = tissueDensity['CSF']

    # tissue fractions
        self.f_GM = tissueFractions['GM']
        self.f_WM = tissueFractions['WM']
        self.f_CSF = tissueFractions['CSF']

    # Calculate T2 relaxation terms 
        self.R_H2O_GM = np.exp(-TE/T2['H2O_GM'])
        self.R_H2O_WM = np.exp(-TE/T2['H2O_WM'])
        self.R_H2O_CSF = np.exp(-TE/T2['H2O_CSF'])
        self.R_M = np.exp(-TE/T2['METAB'])

def selectT2Values(centralFreq):
    """ Select T2 values based on field strength (7T or 3T)"""
    field = centralFreq/H1_gamma
    if  field>6.5 and field<7.5:
        return STANDARD_T2['7T']
    elif field>2.5 and field<3.5:
        return STANDARD_T2['3T']
    else:
        raise ValueError(f'No stored T2 values for {field}T scanner. Specify values manually.')

def loadDefaultQuantificationInfo(TE,tissueFractions,centralFreq):
    """ Create a QuantificationInfo object given TE, tissue fractions and central frequency in MHz."""
    T2 = selectT2Values(centralFreq)

    return QuantificationInfo(TE,T2,tissueFractions)