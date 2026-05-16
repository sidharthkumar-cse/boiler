def get_water_level(Vdw, A):
    """
    Calculate water level L from water volume Vdw and cross-sectional area A.
    
    Relation:
    Vdw = A * L
    => L = Vdw / A
    """
    return Vdw / A

def get_steam_volume(Vtotal, Vdw):
    """
    Calculate steam volume Vds from total volume Vtotal and water volume Vdw.
    
    Relation:
    Vds = Vtotal - Vdw
    """
    return Vtotal - Vdw
