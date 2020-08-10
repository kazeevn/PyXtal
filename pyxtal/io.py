"""
This module handles reading and write crystal files.
"""
from pyxtal.constants import deg, logo
import numpy as np
from pyxtal.symmetry import Group

def write_cif(struc, filename=None, header="", permission='w', sym_num=None):
    """
    Export the structure in cif format

    Args:
        struc: pyxtal structure object
        filename: path of the structure file 
        header: additional information
        permission: write('w') or append('a+') to the given file
        sym_num: the number of symmetry operations, None means writing all symops
    
    """
    if sym_num is None:
        l_type = struc.group.lattice_type
        symbol = struc.group.symbol
        number = struc.group.number
        G1 = struc.group.Wyckoff_positions[0]

    else: #P1 symmetry
        l_type = 'triclinic'
        symbol = 'P1'
        number = 1
        G1 = Group(1).Wyckoff_positions[0]

    if hasattr(struc, 'mol_sites'):
        sites = struc.mol_sites
        molecule = True
    else:
        sites = struc.atom_sites
        molecule = False

    change_set = False
    if l_type == 'monoclinic':
        if G1 != sites[0].wp.generators:
            symbol = symbol.replace('c','n')
            change_set = True
    
    lines = logo
    lines += 'data_' + header + '\n'
    if hasattr(struc, "energy"):
        lines += '#Energy: {:} eV/cell\n'.format(struc.energy/sum(struc.numMols))

    lines += "\n_symmetry_space_group_name_H-M '{:s}'\n".format(symbol)
    lines += '_symmetry_Int_Tables_number      {:>15d}\n'.format(number)
    lines += '_symmetry_cell_setting           {:>15s}\n'.format(l_type)
    lines += '_cell_length_a        {:12.6f}\n'.format(struc.lattice.a)
    lines += '_cell_length_b        {:12.6f}\n'.format(struc.lattice.b)
    lines += '_cell_length_c        {:12.6f}\n'.format(struc.lattice.c)
    lines += '_cell_angle_alpha     {:12.6f}\n'.format(deg*struc.lattice.alpha)
    lines += '_cell_angle_beta      {:12.6f}\n'.format(deg*struc.lattice.beta)
    lines += '_cell_angle_gamma     {:12.6f}\n'.format(deg*struc.lattice.gamma)

    lines += '\nloop_\n'
    lines += ' _symmetry_equiv_pos_site_id\n'
    lines += ' _symmetry_equiv_pos_as_xyz\n'
    if not change_set:
        wps = G1
    else:
        wps = sites[0].wp.generators

    for i, op in enumerate(wps):
        lines += "{:d} '{:s}'\n".format(i+1, op.as_xyz_string())

    lines += '\nloop_\n'
    lines += ' _atom_site_label\n'
    lines += ' _atom_site_fract_x\n'
    lines += ' _atom_site_fract_y\n'
    lines += ' _atom_site_fract_z\n'
    lines += ' _atom_site_occupancy\n'

    for site in sites:
        if molecule:
            if sym_num is None:
                coords, species = site._get_coords_and_species(first=True)
            else:
                coords = None
                species = []
                for id in range(sym_num):
                    mol = site.get_mol_object(id)
                    tmp = mol.cart_coords.dot(site.inv_lattice)
                    if coords is None:
                        coords = tmp
                    else:
                        coords = np.append(coords, tmp, axis=0)
                    species.extend([s.value for s in mol.species])
                #coords, species = site._get_coords_and_species(ids=sym_num)
        else:
            coords, species = [site.position], [site.specie]
        for specie, coord in zip(species, coords):
            lines += '{:6s}  {:12.6f}{:12.6f}{:12.6f} 1\n'.format(specie, *coord)
    lines +='#END\n\n'
    

    if filename is None:
        return lines
    else:
        with open(filename, permission) as f:
            f.write(lines)
        return

from pymatgen.core.structure import Structure, Molecule
from pymatgen.core.bonds import CovalentBond
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pyxtal.wyckoff_site import mol_site, WP_merge
from pyxtal.molecule import pyxtal_molecule, Orientation, compare_mol_connectivity
from pyxtal.symmetry import Wyckoff_position, Group
from pyxtal.lattice import Lattice


class structure_from_ext():
    
    def __init__(self, struc, ref_mol=None, tol=0.2):

        """
        extract the mol_site information from the give cif file 
        and reference molecule
    
        Args: 
            struc: cif/poscar file or a Pymatgen Structure object
            ref_mol: xyz file or a reference Pymatgen molecule object
            tol: scale factor for covalent bond distance
        
    """
        if isinstance(ref_mol, str):
            ref_mol = Molecule.from_file(ref_mol)
        elif isinstance(ref_mol, Molecule):
            ref_mol = ref_mol
        else:
            print(type(ref_mol))
            raise NameError("reference molecule cannot be defined")

    
        if isinstance(struc, str):
            pmg_struc = Structure.from_file(struc)
        elif isinstance(struc, Structure):
            pmg_struc = struc
        else:
            print(type(struc))
            raise NameError("input structure cannot be intepretted")

        self.ref_mol = ref_mol.get_centered_molecule()
        self.tol = tol

        sga = SpacegroupAnalyzer(pmg_struc)
        ops = sga.get_space_group_operations()
        self.wyc, perm = Wyckoff_position.from_symops(ops)

        if self.wyc is not None:
            self.group = Group(self.wyc.number)
            if perm != [0,1,2]:
                lattice = Lattice.from_matrix(pmg_struc.lattice.matrix, self.group.lattice_type)
                latt = lattice.swap_axis(ids=perm, random=False).get_matrix()
                coor = pmg_struc.frac_coords[perm]
                pmg_struc = Structure(latt, pmg_struc.atomic_numbers, coor)
            coords, numbers = search_molecule_in_crystal(pmg_struc, self.tol)
            self.molecule = Molecule(numbers, coords)
            self.pmg_struc = pmg_struc
            self.lattice = Lattice.from_matrix(pmg_struc.lattice.matrix, self.group.lattice_type)
        else:
            raise ValueError("Cannot find the space group matching the symmetry operation")

    
    def make_mol_site(self, ref=False):
        if ref:
            mol = self.ref_mol
            ori = self.ori
        else:
            mol = self.molecule
            ori = Orientation(np.eye(3))
        pmol = pyxtal_molecule(mol)
        # needs to fix coord0
        site = mol_site(pmol,
                        self.position, 
                        ori,
                        self.wyc, 
                        self.lattice,
                        )
        return site

    def align(self):
        """
        compute the orientation wrt the reference molecule
        """
        from openbabel import pybel, openbabel

        m1 = pybel.readstring('xyz', self.ref_mol.to('xyz'))
        m2 = pybel.readstring('xyz', self.molecule.to('xyz'))
        aligner = openbabel.OBAlign(True, False)
        aligner.SetRefMol(m1.OBMol)
        aligner.SetTargetMol(m2.OBMol)
        aligner.Align()
        print("RMSD: ", aligner.GetRMSD())
        rot=np.zeros([3,3])
        for i in range(3):
            for j in range(3):
                rot[i,j] = aligner.GetRotMatrix().Get(i,j)
        coord2 = self.molecule.cart_coords
        coord2 -= np.mean(coord2, axis=0)
        coord3 = rot.dot(coord2.T).T + np.mean(self.ref_mol.cart_coords, axis=0)
        self.mol_aligned = Molecule(self.ref_mol.atomic_numbers, coord3)
        self.ori = Orientation(rot)
   
    def match(self):
        """
        Check the two molecular graphs are isomorphic
        """
        match, mapping = compare_mol_connectivity(self.ref_mol, self.molecule)
        if not match:
            print(self.ref_mol)
            print(self.molecule)
            return False
        else:
            # resort the atomic number for molecule 1
            order = [mapping[i] for i in range(len(self.ref_mol))]
            numbers = np.array(self.molecule.atomic_numbers)
            numbers = numbers[order].tolist()
            coords = self.molecule.cart_coords[order]
            position = np.mean(coords, axis=0).dot(self.lattice.inv_matrix)
            position -= np.floor(position)
            # check if molecule is on the special wyckoff position
            if len(self.pmg_struc)/len(self.molecule) < len(self.wyc):
                # todo: Get the subgroup to display
                position, wp, _ = WP_merge(position, self.lattice.matrix, self.wyc, 2.0)
                self.wyc = wp
            self.position = position
            self.molecule = Molecule(numbers, coords-np.mean(coords, axis=0))
            self.align()
            return True

    def show(self, overlay=True):
        from pyxtal.viz import display_molecules
        if overlay:
            return display_molecules([self.ref_mol, self.mol_aligned])
        else:
            return display_molecules([self.ref_mol, self.molecule])


def search_molecule_in_crystal(struc, tol=0.2, keep_order=False, absolute=True):
    """
    This is a function to perform a search to find the molecule
    in a Pymatgen crystal structure

    Args:
        struc: Pymatgen Structure
        keep_order: whether or not use the orignal sequence
        absolute: whether or not output absolute coordindates

    Returns:
        coords: fractional coordinates
        numbers: atomic numbers
    """
    def check_one_layer(struc, sites0, visited):
        new_members = []
        for site0 in sites0:
            sites_add, visited = check_one_site(struc, site0, visited)
            new_members.extend(sites_add)
        return new_members, visited
    
    def check_one_site(struc, site0, visited):
        neigh_sites = struc.get_neighbors(site0, 3.0)
        ids = [m.index for m in visited]
        sites_add = []
        ids_add = []

        for site1 in neigh_sites:
            if (site1.index not in ids+ids_add):
                if CovalentBond.is_bonded(site0, site1, tol):
                    sites_add.append(site1)
                    ids_add.append(site1.index)
        if len(sites_add) > 0:
            visited.extend(sites_add)

        return sites_add, visited

    first_site = struc.sites[0]
    first_site.index = 0 #assign the index
    visited = [first_site] 
    ids = [0]

    n_iter, max_iter = 0, len(struc)
    while n_iter < max_iter:
        if n_iter == 0:
            new_sites, visited = check_one_site(struc, first_site, visited)
        else:
            new_sites, visited = check_one_layer(struc, new_sites, visited)
        n_iter += 1
        if len(new_sites)==0:
            break
    
    coords = [s.coords for s in visited]
    numbers = [s.specie.number for s in visited]
    
    if keep_order:
        ids = [s.index for s in visited]
        seq = np.argsort(ids)
        coords = coords[seq]
        numbers = numbers[seq]

    if not absolute:
        coords = coords.dot(struc.lattice.inv)
    return coords, numbers

#seed = structure_from_cif("254385.cif", "1.xyz")
#if seed.match():
#    print(seed.pmg_struc)

"""
Symmetry transformation
group -> subgroup
At the moment we only consider 
for multiplicity 2: P-1, P21, P2, Pm and Pc
to add: for multiplicity 4: P21/c, P212121
Permutation is allowed
"""





