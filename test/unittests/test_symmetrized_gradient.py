#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Aug 12 11:26:41 2019

@author: omaier
"""

import pyqmri
try:
    import unittest2 as unittest
except ImportError:
    import unittest
from pyqmri._helper_fun import CLProgram as Program
from pkg_resources import resource_filename
import pyopencl.array as clarray
import numpy as np


DTYPE = np.complex64
DTYPE_real = np.float32
ATOL=1e-7
RTOL=1e-4

class tmpArgs():
    pass


def setupPar(par):
    par["NScan"] = 10
    par["NC"] = 15
    par["NSlice"] = 10
    par["dimX"] = 128
    par["dimY"] = 128
    par["Nproj"] = 21
    par["N"] = 256
    par["unknowns_TGV"] = 2
    par["unknowns_H1"] = 0
    par["unknowns"] = 2
    par["dz"] = 1
    par["weights"] = np.array([1, 1])


class SymmetrizedGradientTest(unittest.TestCase):
    def setUp(self):
        parser = tmpArgs()
        parser.streamed = False
        parser.devices = -1
        parser.use_GPU = True

        par = {}
        pyqmri.pyqmri._setupOCL(parser, par)
        setupPar(par)
        if DTYPE == np.complex128:
            file = open(
                    resource_filename(
                        'pyqmri', 'kernels/OpenCL_Kernels_double.c'))
        else:
            file = open(
                    resource_filename(
                        'pyqmri', 'kernels/OpenCL_Kernels.c'))
        prg = Program(
            par["ctx"][0],
            file.read())
        file.close()

        self.weights = par["weights"]

        self.symgrad = pyqmri.operator.OperatorFiniteSymGradient(
            par, prg,
            DTYPE=DTYPE,
            DTYPE_real=DTYPE_real)

        self.symgradin = np.random.randn(par["unknowns"], par["NSlice"],
                                         par["dimY"], par["dimX"], 4) +\
            1j * np.random.randn(par["unknowns"], par["NSlice"],
                                 par["dimY"], par["dimX"], 4)
        self.symdivin = np.random.randn(par["unknowns"], par["NSlice"],
                                        par["dimY"], par["dimX"], 8) +\
            1j * np.random.randn(par["unknowns"], par["NSlice"],
                                 par["dimY"], par["dimX"], 8)
        self.symgradin = self.symgradin.astype(DTYPE)
        self.symdivin = self.symdivin.astype(DTYPE)
        self.dz = par["dz"]
        self.queue = par["queue"][0]

    def test_sym_grad_outofplace(self):
        gradx = np.zeros_like(self.symgradin)
        grady = np.zeros_like(self.symgradin)
        gradz = np.zeros_like(self.symgradin)

        gradx[..., 1:, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-2), axis=-2), axis=-2)
        grady[..., 1:, :, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-3), axis=-3), axis=-3)
        gradz[:, 1:, ...] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-4), axis=-4), axis=-4)

        symgrad = np.stack((gradx[..., 0],
                            grady[..., 1],
                            gradz[..., 2]*self.dz,
                            1/2 * (gradx[..., 1] + grady[..., 0]),
                            1/2 * (gradx[..., 2] + gradz[..., 0]*self.dz),
                            1/2 * (grady[..., 2] + gradz[..., 1]*self.dz)),
                           axis=-1)
        symgrad *= self.weights[:, None, None, None, None]

        inp = clarray.to_device(self.queue, self.symgradin)
        outp = self.symgrad.fwdoop(inp)
        outp = outp.get()

        np.testing.assert_allclose(outp[..., :6], symgrad, rtol=RTOL, atol=ATOL)

    def test_sym_grad_inplace(self):
        gradx = np.zeros_like(self.symgradin)
        grady = np.zeros_like(self.symgradin)
        gradz = np.zeros_like(self.symgradin)

        gradx[..., 1:, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-2), axis=-2), axis=-2)
        grady[..., 1:, :, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-3), axis=-3), axis=-3)
        gradz[:, 1:, ...] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-4), axis=-4), axis=-4)

        symgrad = np.stack((gradx[..., 0],
                            grady[..., 1],
                            gradz[..., 2]*self.dz,
                            1/2 * (gradx[..., 1] + grady[..., 0]),
                            1/2 * (gradx[..., 2] + gradz[..., 0]*self.dz),
                            1/2 * (grady[..., 2] + gradz[..., 1]*self.dz)),
                           axis=-1)
        symgrad *= self.weights[:, None, None, None, None]
        inp = clarray.to_device(self.queue, self.symgradin)
        outp = clarray.to_device(self.queue, self.symdivin)
        outp.add_event(self.symgrad.fwd(outp, inp))
        outp = outp.get()

        np.testing.assert_allclose(outp[..., :6], symgrad, rtol=RTOL, atol=ATOL)

    def test_adj_outofplace(self):
        inpgrad = clarray.to_device(self.queue, self.symgradin)
        inpdiv = clarray.to_device(self.queue, self.symdivin)

        outgrad = self.symgrad.fwdoop(inpgrad)
        outdiv = self.symgrad.adjoop(inpdiv)

        outgrad = outgrad.get()
        outdiv = outdiv.get()
        a1 = np.vdot(outgrad[..., :3].flatten(),
                     self.symdivin[..., :3].flatten())/self.symgradin.size*4
        a2 = 2*np.vdot(outgrad[..., 3:6].flatten(),
                       self.symdivin[..., 3:6].flatten())/self.symgradin.size*4
        a = a1+a2
        b = np.vdot(self.symgradin[..., :3].flatten(),
                    -outdiv[..., :3].flatten())/self.symgradin.size*4

        print("Adjointness: %.2e +1j %.2e" % ((a - b).real, (a - b).imag))

        np.testing.assert_allclose(a, b, rtol=RTOL, atol=ATOL)

    def test_adj_inplace(self):
        inpgrad = clarray.to_device(self.queue, self.symgradin)
        inpdiv = clarray.to_device(self.queue, self.symdivin)

        outgrad = clarray.zeros_like(inpdiv)
        outdiv = clarray.zeros_like(inpgrad)

        outgrad.add_event(self.symgrad.fwd(outgrad, inpgrad))
        outdiv.add_event(self.symgrad.adj(outdiv, inpdiv))

        outgrad = outgrad.get()
        outdiv = outdiv.get()

        a1 = np.vdot(outgrad[..., :3].flatten(),
                     self.symdivin[..., :3].flatten())/self.symgradin.size*4
        a2 = 2*np.vdot(outgrad[..., 3:6].flatten(),
                       self.symdivin[..., 3:6].flatten())/self.symgradin.size*4
        a = a1+a2
        b = np.vdot(self.symgradin[..., :3].flatten(),
                    -outdiv[..., :3].flatten())/self.symgradin.size*4

        print("Adjointness: %.2e +1j %.2e" % ((a - b).real, (a - b).imag))

        np.testing.assert_allclose(a, b, rtol=RTOL, atol=ATOL)


class SymmetrizedGradientStreamedTest(unittest.TestCase):
    def setUp(self):
        parser = tmpArgs()
        parser.streamed = True
        parser.devices = -1
        parser.use_GPU = True

        par = {}
        pyqmri.pyqmri._setupOCL(parser, par)
        setupPar(par)
        if DTYPE == np.complex128:
            file = resource_filename(
                        'pyqmri', 'kernels/OpenCL_Kernels_double_streamed.c')
        else:
            file = resource_filename(
                        'pyqmri', 'kernels/OpenCL_Kernels_streamed.c')

        prg = []
        for j in range(len(par["ctx"])):
          with open(file) as myfile:
            prg.append(Program(
                par["ctx"][j],
                myfile.read()))

        par["par_slices"] = 1

        self.weights = par["weights"]

        self.symgrad = pyqmri.operator.OperatorFiniteSymGradientStreamed(
            par, prg,
            DTYPE=DTYPE,
            DTYPE_real=DTYPE_real)

        self.symgradin = np.random.randn(par["NSlice"], par["unknowns"],
                                         par["dimY"], par["dimX"], 4) +\
            1j * np.random.randn(par["NSlice"], par["unknowns"],
                                 par["dimY"], par["dimX"], 4)
        self.symdivin = np.random.randn(par["NSlice"], par["unknowns"],
                                        par["dimY"], par["dimX"], 8) +\
            1j * np.random.randn(par["NSlice"], par["unknowns"],
                                 par["dimY"], par["dimX"], 8)
        self.symgradin = self.symgradin.astype(DTYPE)
        self.symdivin = self.symdivin.astype(DTYPE)
        self.dz = par["dz"]

    def test_grad_outofplace(self):
        gradx = np.zeros_like(self.symgradin)
        grady = np.zeros_like(self.symgradin)
        gradz = np.zeros_like(self.symgradin)

        gradx[..., 1:, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-2), axis=-2), axis=-2)
        grady[..., 1:, :, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-3), axis=-3), axis=-3)
        gradz[1:, ...] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=0), axis=0), axis=0)

        symgrad = np.stack((gradx[..., 0],
                            grady[..., 1],
                            gradz[..., 2]*self.dz,
                            1/2 * (gradx[..., 1] + grady[..., 0]),
                            1/2 * (gradx[..., 2] + gradz[..., 0]*self.dz),
                            1/2 * (grady[..., 2] + gradz[..., 1]*self.dz)),
                           axis=-1)
        symgrad *= self.weights[None, :, None, None, None]
        outp = self.symgrad.fwdoop([[self.symgradin]])

        np.testing.assert_allclose(outp[..., :6], symgrad, rtol=RTOL, atol=ATOL)

    def test_grad_inplace(self):
        gradx = np.zeros_like(self.symgradin)
        grady = np.zeros_like(self.symgradin)
        gradz = np.zeros_like(self.symgradin)

        gradx[..., 1:, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-2), axis=-2), axis=-2)
        grady[..., 1:, :, :] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=-3), axis=-3), axis=-3)
        gradz[1:, ...] = -np.flip(
            np.diff(
                np.flip(self.symgradin, axis=0), axis=0), axis=0)

        symgrad = np.stack((gradx[..., 0],
                            grady[..., 1],
                            gradz[..., 2]*self.dz,
                            1/2 * (gradx[..., 1] + grady[..., 0]),
                            1/2 * (gradx[..., 2] + gradz[..., 0]*self.dz),
                            1/2 * (grady[..., 2] + gradz[..., 1]*self.dz)),
                           axis=-1)
        symgrad *= self.weights[None, :, None, None, None]
        outp = np.zeros_like(self.symdivin)

        self.symgrad.fwd([outp], [[self.symgradin]])

        np.testing.assert_allclose(outp[..., :6], symgrad, rtol=RTOL, atol=ATOL)

    def test_adj_outofplace(self):

        outgrad = self.symgrad.fwdoop([[self.symgradin]])
        outdiv = self.symgrad.adjoop([[self.symdivin]])

        a1 = np.vdot(outgrad[..., :3].flatten(),
                     self.symdivin[..., :3].flatten())/self.symgradin.size*4
        a2 = 2*np.vdot(outgrad[..., 3:6].flatten(),
                       self.symdivin[..., 3:6].flatten())/self.symgradin.size*4
        a = a1+a2
        b = np.vdot(self.symgradin[..., :3].flatten(),
                    -outdiv[..., :3].flatten())/self.symgradin.size*4

        print("Adjointness: %.2e +1j %.2e" % ((a - b).real, (a - b).imag))

        np.testing.assert_allclose(a, b, rtol=RTOL, atol=ATOL)

    def test_adj_inplace(self):

        outgrad = np.zeros_like(self.symdivin)
        outdiv = np.zeros_like(self.symgradin)

        self.symgrad.fwd([outgrad], [[self.symgradin]])
        self.symgrad.adj([outdiv], [[self.symdivin]])

        a1 = np.vdot(outgrad[..., :3].flatten(),
                     self.symdivin[..., :3].flatten())/self.symgradin.size*4
        a2 = 2*np.vdot(outgrad[..., 3:6].flatten(),
                       self.symdivin[..., 3:6].flatten())/self.symgradin.size*4
        a = a1+a2
        b = np.vdot(self.symgradin[..., :3].flatten(),
                    -outdiv[..., :3].flatten())/self.symgradin.size*4

        print("Adjointness: %.2e +1j %.2e" % ((a - b).real, (a - b).imag))

        np.testing.assert_allclose(a, b, rtol=RTOL, atol=ATOL)

class SymGradientTestICTGV(unittest.TestCase):
    def setUp(self):
        parser = tmpArgs()
        parser.streamed = False
        parser.devices = -1
        parser.use_GPU = True

        par = {}
        pyqmri.pyqmri._setupOCL(parser, par)
        setupPar(par)
        if DTYPE == np.complex128:
            file = resource_filename(
                        'pyqmri', 'kernels/OpenCL_Kernels_double.c')
        else:
            file = resource_filename(
                        'pyqmri', 'kernels/OpenCL_Kernels.c')

        prg = []
        for j in range(len(par["ctx"])):
          with open(file) as myfile:
            prg.append(Program(
                par["ctx"][j],
                myfile.read()))
        prg = prg[0]
        par["unknowns"] = par["NScan"]
        
        self.weights = par["weights"]
        
        dt = np.random.randn(par["NScan"]-1)*10

        self.symgrad = pyqmri.operator.OperatorFiniteSpaceTimeSymGradient(
            par, prg,
            DTYPE=DTYPE,
            DTYPE_real=DTYPE_real,
            dt=dt,
            tsweight=0.5)

        self.symgradin = np.random.randn(par["unknowns"], par["NSlice"],
                                         par["dimY"], par["dimX"], 4) +\
            1j * np.random.randn(par["unknowns"], par["NSlice"],
                                 par["dimY"], par["dimX"], 4)
        self.symdivin_diag = np.random.randn(par["unknowns"], par["NSlice"],
                                        par["dimY"], par["dimX"], 4) +\
            1j * np.random.randn(par["unknowns"], par["NSlice"],
                                 par["dimY"], par["dimX"], 4)
        self.symdivin_offdiag = np.random.randn(par["unknowns"], par["NSlice"],
                                        par["dimY"], par["dimX"], 8) +\
            1j * np.random.randn(par["unknowns"], par["NSlice"],
                                 par["dimY"], par["dimX"], 8)
            
        self.symgradin = self.symgradin.astype(DTYPE)
        self.symdivin_diag = self.symdivin_diag.astype(DTYPE)
        self.symdivin_offdiag = self.symdivin_offdiag.astype(DTYPE)
        self.dz = par["dz"]
        self.queue = par["queue"][0]

    def test_adj_outofplace(self):
        inpgrad = clarray.to_device(self.queue, self.symgradin)
        inpdiv_diag = clarray.to_device(self.queue, self.symdivin_diag)
        inpdiv_offdiag = clarray.to_device(self.queue, self.symdivin_offdiag)

        outgrad_diag, outgrad_offdiag = self.symgrad.fwdoop(inpgrad)
        outdiv = self.symgrad.adjoop([inpdiv_diag, inpdiv_offdiag])

        outgrad_diag = outgrad_diag.get()
        outgrad_offdiag = outgrad_offdiag.get()
        outdiv = outdiv.get()
        
        a1 = np.vdot(outgrad_diag.flatten(),
                     self.symdivin_diag.flatten())/self.symgradin.size
        
        a2 = 2*np.vdot(outgrad_offdiag[..., :-2].flatten(),
                       self.symdivin_offdiag[..., :-2].flatten())/self.symgradin.size
        a = a1+a2
        b = np.vdot(self.symgradin.flatten(),
                    -outdiv.flatten())/self.symgradin.size

        print("Adjointness: %.2e +1j %.2e" % ((a - b).real, (a - b).imag))

        np.testing.assert_allclose(a, b, rtol=RTOL, atol=ATOL)

    def test_adj_inplace(self):
        inpgrad = clarray.to_device(self.queue, self.symgradin)
        inpdiv_diag = clarray.to_device(self.queue, self.symdivin_diag)
        inpdiv_offdiag = clarray.to_device(self.queue, self.symdivin_offdiag)

        outgrad_diag = clarray.zeros_like(inpdiv_diag)
        outgrad_offdiag = clarray.zeros_like(inpdiv_offdiag)
        outdiv = clarray.zeros_like(inpgrad)

        ev = self.symgrad.fwd([outgrad_diag, outgrad_offdiag], inpgrad)
        outgrad_diag.add_event(ev)
        outgrad_offdiag.add_event(ev)
        outdiv.add_event(self.symgrad.adj(outdiv, [inpdiv_diag, inpdiv_offdiag]))

        outgrad_diag = outgrad_diag.get()
        outgrad_offdiag = outgrad_offdiag.get()
        outdiv = outdiv.get()

        a1 = np.vdot(outgrad_diag.flatten(),
                      self.symdivin_diag.flatten())/self.symgradin.size
        a2 = 2*np.vdot(outgrad_offdiag[..., :-2].flatten(),
                        self.symdivin_offdiag[..., :-2].flatten())/self.symgradin.size
        a = a1+a2
        b = np.vdot(self.symgradin.flatten(),
                    -outdiv.flatten())/self.symgradin.size

        print("Adjointness: %.2e +1j %.2e" % ((a - b).real, (a - b).imag))

        np.testing.assert_allclose(a, b, rtol=RTOL, atol=ATOL)

if __name__ == '__main__':
    unittest.main()
