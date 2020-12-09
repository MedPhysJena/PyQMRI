#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from pyqmri.models.template import BaseModel, constraints
plt.ion()



class Model(BaseModel):
    def __init__(self, par):
        super().__init__(par)
        self.constraints = []
        self.t = par["t"]
        self.b = par["b"]
        if "b0" in par.keys():
            self.b0 = par["b0"]
        else:
            self.b0 = self.b[0]

        if len(self.t.shape) < 2:
            self.b = self.b[None]
            self.t = self.t[None]

        self.numT1Scale = len(self.b)

        par["unknowns_TGV"] = len(self.b) + len(self.b) + len(self.b)
        par["unknowns_H1"] = 0
        par["unknowns"] = par["unknowns_TGV"]+par["unknowns_H1"]

        self.unknowns = par["unknowns"]
        
        t1min = 0 #np.min(self.t)/3

        for j in range(par["unknowns"]):
            self.uk_scale.append(1)
            
        for j in range(self.numT1Scale):
            self.constraints.append(
                constraints(0,
                            1000,
                            False))
        for j in range(self.numT1Scale):
            self.constraints.append(
                constraints(0,
                            5,
                            True))
        for j in range(self.numT1Scale):
            self.constraints.append(
                constraints(t1min,
                            2000/(j+1),
                            True))
        self._ind1 = 0
        self._ind2 = 0
        self._labels = []
        for j in range(len(self.b)):
            self._labels.append(
                "Field "+str(np.round(self.b[j]*1e3, 2))+" mT")

    def rescale(self, x):
        tmp_x = np.copy(x)
        ukname = []
        for j in range(self.numT1Scale):
            tmp_x[j] *= self.uk_scale[j]
            ukname.append("C_"+str(1+j))
        for j in range(self.numT1Scale):
            tmp_x[self.numT1Scale+j] *= self.uk_scale[self.numT1Scale+j]
            ukname.append("alpha_"+str(1+j))
        for j in range(self.numT1Scale):
            tmp_x[-self.numT1Scale+j] *= self.uk_scale[-self.numT1Scale+j]
            ukname.append("T1_"+str(1+j))
        const = []
        for constrained in self.constraints:
            const.append(constrained.real)
        return {"data": tmp_x,
                "unknown_name": ukname,
                "real_valued": const}

    def _execute_forward_3D(self, x):
        S = np.zeros(
            (self.NScan, self.NSlice, self.dimY, self.dimX),
            dtype=self._DTYPE)
        t = self.t[0][:, None, None, None]
        for j in range(self.numT1Scale):
            offset = len(self.t[j])
            t = self.t[j][:, None, None, None]
            S[offset*(j):offset*(j+1)] = (
                x[j] * self.uk_scale[j]
                * (-self.b0 * x[self.numT1Scale+j]*self.uk_scale[self.numT1Scale+j] *
                   np.exp(-t / (x[-self.numT1Scale+j] * self.uk_scale[-self.numT1Scale+j]))
                   + (1 - np.exp(-t / (x[-self.numT1Scale+j] * self.uk_scale[-self.numT1Scale+j])))
                   * self.b[j])
                )
        S[~np.isfinite(S)] = 1e-20
        S = np.array(S, dtype=self._DTYPE)
        return S

    def _execute_gradient_3D(self, x):

        gradC = self._gradC(x)
        gradAlpha = self._gradAlpha(x)
        gradT1 = self._gradT1(x)

        grad = np.concatenate((gradC, gradAlpha, gradT1), axis=0)
        return grad

    def _gradC(self, x):
        grad = np.zeros(
            (self.numT1Scale, self.NScan, self.NSlice, self.dimY, self.dimX),
            dtype=self._DTYPE)
        t = self.t[0][:, None, None, None]
        for j in range(self.numT1Scale):
            offset = len(self.t[j])
            t = self.t[j][:, None, None, None]
            grad[j, offset*(j):offset*(j+1)] = (
                self.uk_scale[j]
                * (-self.b0 * x[self.numT1Scale+j]*self.uk_scale[self.numT1Scale+j] *
                   np.exp(-t / (x[-self.numT1Scale+j] * self.uk_scale[-self.numT1Scale+j]))
                   + (1 - np.exp(-t / (x[-self.numT1Scale+j] * self.uk_scale[-self.numT1Scale+j])))
                   * self.b[j])
                )
        grad[~np.isfinite(grad)] = 1e-20

        return grad

    def _gradAlpha(self, x):
        grad = np.zeros(
            (self.numT1Scale, self.NScan, self.NSlice, self.dimY, self.dimX),
            dtype=self._DTYPE)
        t = self.t[0][:, None, None, None]
        for j in range(self.numT1Scale):
            offset = len(self.t[j])
            t = self.t[j][:, None, None, None]
            grad[j, offset*(j):offset*(j+1)] = (
                x[j] * self.uk_scale[j]*self.uk_scale[self.numT1Scale+j]
                * (-self.b0 *
                   np.exp(-t / (x[-self.numT1Scale+j] * self.uk_scale[-self.numT1Scale+j]))
                   )
                )
        grad[~np.isfinite(grad)] = 1e-20

        return grad

    def _gradT1(self, x):
        grad = np.zeros(
            (self.numT1Scale, self.NScan, self.NSlice, self.dimY, self.dimX),
            dtype=self._DTYPE)
        t = self.t[0][:, None, None, None]
        for j in range(self.numT1Scale):
            offset = len(self.t[j])
            t = self.t[j][:, None, None, None]
            grad[j, (j)*offset:(j+1)*offset] = (
                x[j]*self.uk_scale[j]*(
                    -self.b0*t*x[self.numT1Scale+j]*self.uk_scale[self.numT1Scale+j]
                    * np.exp(-t/(x[-self.numT1Scale+j]*self.uk_scale[-self.numT1Scale+j]))
                    - self.b[j]*t
                    * np.exp(-t/(x[-self.numT1Scale+j]*self.uk_scale[-self.numT1Scale+j]))
                    )
                )/(x[-self.numT1Scale+j]**2*self.uk_scale[-self.numT1Scale+j])
        grad[~np.isfinite(grad)] = 1e-20

        return grad

    def plot_unknowns(self, x, dim_2D=False):
        unknowns = self.rescale(x)
        tmp_x = unknowns["data"]
        uknames = unknowns["unknown_name"]

        images = np.abs(self._execute_forward_3D(x) / self.dscale)
        images = np.reshape(images, self.t.shape+images.shape[-3:])

        tmp_x[:self.numT1Scale] = np.abs(tmp_x[:self.numT1Scale])/self.dscale
        tmp_x = np.abs(tmp_x)

        if dim_2D:
            pass
        else:
            if not self._figure:
                self.ax = []
                plot_dim = int(np.ceil(np.sqrt(len(self.uk_scale))))
                plt.ion()
                self._figure = plt.figure(figsize=(12, 6))
                self._figure.subplots_adjust(hspace=0.3, wspace=0)
                wd_ratio = np.tile([1, 1 / 20, 1 / (5)], plot_dim)
                self.gs = gridspec.GridSpec(
                    plot_dim+1, 3*plot_dim,
                    width_ratios=wd_ratio, hspace=0.3, wspace=0)
                self._figure.tight_layout()
                self._figure.patch.set_facecolor(plt.cm.viridis.colors[0])
                for grid in self.gs:
                    self.ax.append(plt.subplot(grid))
                    self.ax[-1].axis('off')
                self._plot = []
                for j in range(len(self.uk_scale)):
                    self._plot.append(
                        self.ax[3 * j].imshow(
                            tmp_x[j, int(self.NSlice / 2), ...]))
                    self.ax[3 *
                            j].set_title(uknames[j], color='white')
                    self.ax[3 * j + 1].axis('on')
                    cbar = self._figure.colorbar(
                        self._plot[j], cax=self.ax[3 * j + 1])
                    cbar.ax.tick_params(labelsize=12, colors='white')
                    for spine in cbar.ax.spines:
                        cbar.ax.spines[spine].set_color('white')
                plt.draw()
                plt.pause(1e-10)
                self._figure.canvas.mpl_connect(
                    'button_press_event',
                    self.onclick)

                self.plot_ax = plt.subplot(self.gs[-1, :])
                self.plot_ax.set_title("Time course", color='w')
                self.time_course_ref = []
                for j in range(len(self.b)):
                    self.time_course_ref.append(self.plot_ax.plot(
                        self.t[j], np.real(
                            self.images[j, :,
                                        int(self.NSlice/2),
                                        self._ind2, self._ind1]).T,
                        'x', label=self._labels[j])[0])
                self.plot_ax.set_prop_cycle(None)
                legend = self.plot_ax.legend(frameon=True, framealpha=0.3)
                for _txt in legend.texts:
                    _txt.set_alpha(0.3)
                for lh in legend.legendHandles:
                    lh._legmarker.set_alpha(0.3)
                self.time_course = self.plot_ax.plot(
                    self.t.T, np.real(
                        images[..., int(self.NSlice/2),
                               self._ind2, self._ind1]).T)
                self.plot_ax.set_ylim(
                    np.minimum(np.real(images[...,
                                              int(self.NSlice/2),
                                              self._ind2,
                                              self._ind1]).min(),
                               np.real(self.images[...,
                                                   int(self.NSlice/2),
                                                   self._ind2,
                                                   self._ind1]).min()),
                    1.2*np.maximum(np.real(images[...,
                                                  int(self.NSlice/2),
                                                  self._ind2,
                                                  self._ind1]).max(),
                                   np.real(self.images[...,
                                                       int(self.NSlice/2),
                                                       self._ind2,
                                                       self._ind1]).max()))
                for spine in self.plot_ax.spines:
                    self.plot_ax.spines[spine].set_color('white')
                self.plot_ax.xaxis.label.set_color('white')
                self.plot_ax.yaxis.label.set_color('white')
                self.plot_ax.tick_params(axis='both', colors='white')

                plt.draw()
                plt.show()
                plt.pause(1e-4)
            else:
                for j in range(len(self.uk_scale)):
                    self._plot[j].set_data(
                        tmp_x[j, int(self.NSlice / 2), ...])
                    self._plot[j].set_clim(
                        [tmp_x[j].min(), tmp_x[j].max()])

                for j in range(len(self.b)):
                    self.time_course[j].set_ydata(
                        np.real(images[
                            j, :, int(self.NSlice/2), self._ind2, self._ind1]))
                self.plot_ax.set_ylim(
                    np.minimum(np.real(images[...,
                                              int(self.NSlice/2),
                                              self._ind2,
                                              self._ind1]).min(),
                               np.real(self.images[...,
                                                   int(self.NSlice/2),
                                                   self._ind2,
                                                   self._ind1]).min()),
                    1.2*np.maximum(np.real(images[...,
                                                  int(self.NSlice/2),
                                                  self._ind2,
                                                  self._ind1]).max(),
                                   np.real(self.images[...,
                                                       int(self.NSlice/2),
                                                       self._ind2,
                                                       self._ind1]).max()))
                plt.draw()
                plt.pause(1e-10)

    def onclick(self, event):
        if event.inaxes in self.ax[::3]:
            self._ind1 = int(event.xdata)
            self._ind2 = int(event.ydata)
            for j in range(len(self.b)):
                self.time_course_ref[j].set_ydata(np.real(
                        self.images[j, :,
                                    int(self.NSlice/2),
                                    self._ind2, self._ind1]).T)

    def computeInitialGuess(self, *args):
        self.dscale = args[1]
        self.images = np.reshape(np.abs(args[0]/args[1]),
                                 self.t.shape+args[0].shape[-3:])
        test_M0 = []
        for j in range(self.numT1Scale):
            test_M0.append(0.1*np.ones(
                (self.NSlice, self.dimY, self.dimX), dtype=self._DTYPE))
            self.constraints[j].update(1/args[1])
        test_Xi = []
        for j in range(self.numT1Scale):
            test_Xi.append(
                1 *
                np.ones(
                    (self.NSlice, self.dimY, self.dimX), dtype=self._DTYPE))
 
        test_R1 = []
        # self.b *= args[1]
        for j in range(self.numT1Scale):
            test_R1.append(
                300/(j+1) *
                np.ones(
                    (self.NSlice, self.dimY, self.dimX), dtype=self._DTYPE))


        self.guess = np.array(
            test_M0 + test_Xi + test_R1, dtype=self._DTYPE)
