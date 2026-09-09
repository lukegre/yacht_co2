def virial_exp(sst_degC, pres_atm):
    from numpy import exp

    """
    This script calculates the virial expansion coefficient. It is based on the
    Fugacity Factor calculation in the CO2SYS script originally by Lewis
    and Wallace 1998. Requires pCO2 and temperature in degC for inputs.

    The fugacity of CO2 is calculatied by finding the Fugacity Factor.
    This is based on Weiss, R. F., Marine Chemistry 2:203-215, 1974.

    This assumes that the pressure is at one atmosphere, or close to it.
    Otherwise, the Pres term in the exponent affects the results.
          Weiss, R. F., Marine Chemistry 2:203-215, 1974.
          Delta and B in cm3/mol
    """

    Tk = sst_degC + 273.15
    R = 83.1451

    # d is the cross virial Coefficient B12 for interaction between gases 1 and 2
    # minus the mean of B11 and B22 for 2 our gases
    Delta = (57.7 - 0.118 * Tk)

    # B is the Virial Coefficient for CO2 and can be calculated using Weiss's power series
    B = -1636.75 + 12.0408 * Tk - 0.0327957 * Tk**2 + 3.16528 * 0.00001 * Tk**3

    # For a mixture of CO2 and air at 1 atm (at low CO2 concentrations)
    ve = exp(pres_atm * (B + 2 * Delta) / (R * Tk))

    return ve


def temp_correct(equ_degC, sst_degC):
    """
    pCO2 is corrected for equilibrator vs seawater temperatures
    using the relationship determined in Takahashi (1993).
    """
    from numpy import exp

    delta_temp = sst_degC - equ_degC
    temp_correct_factor = exp(0.0423 * delta_temp)

    return temp_correct_factor