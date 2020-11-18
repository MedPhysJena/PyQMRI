#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pyqmri.models.template import BaseModel, constraints
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import numpy as np
plt.ion()

import ipdb


class Model(BaseModel):
    def __init__(self, par):
        super().__init__(par)
        self.NSlice = par['NSlice']

        self.figure_phase = None

        self.b = np.ones((self.NScan, 1, 1, 1))
        self.dir = par["DWI_dir"].T
        for i in range(self.NScan):
            self.b[i, ...] = par["b_value"][i] * np.ones((1, 1, 1))

        if np.max(self.b) > 100:
            self.b /= 1000

        self.dir = self.dir[:, None, None, None, :]
        par["unknowns_TGV"] = 4
        par["unknowns_H1"] = 0
        par["unknowns"] = par["unknowns_TGV"] + par["unknowns_H1"]
        self.unknowns = par["unknowns_TGV"] + par["unknowns_H1"]
        self.uk_scale = []
        for j in range(self.unknowns):
            self.uk_scale.append(1)

        try:
            self.b0 = np.flip(
                np.transpose(par["file"]["b0"][()], (0, 2, 1)), 0)
        except KeyError:
            print("No b0 image provided")
            self.b0 = None

        self.constraints.append(
            constraints(
                0 / self.uk_scale[0],
                10 / self.uk_scale[0],
                False))
        self.constraints.append(
            constraints(
                (-0 / self.uk_scale[1]),
                (10e0 / self.uk_scale[1]),
                True))
        self.constraints.append(
            constraints(
                (0 / self.uk_scale[2]),
                (1 / self.uk_scale[2]),
                True))
        self.constraints.append(
            constraints(
                (0 / self.uk_scale[3]),
                (150 / self.uk_scale[3]),
                True))

    def rescale(self, x):
        M0 = x[0, ...] * self.uk_scale[0]
        ADC = x[1, ...] * self.uk_scale[1]
        f = x[2, ...] * self.uk_scale[2]
        ADC_ivim = x[3, ...] * self.uk_scale[3]

        return np.array((M0, ADC,
                         f, ADC_ivim))

    def _execute_forward_2D(self, x, islice):
        print("2D Functions not implemented")
        raise NotImplementedError

    def _execute_gradient_2D(self, x, islice):
        print("2D Functions not implemented")
        raise NotImplementedError

    def _execute_forward_3D(self, x):
        #ipdb.set_trace()
        
        ADC = x[1, ...] * self.uk_scale[1]

        S = (x[0, ...] * self.uk_scale[0] * (
                x[2, ...] * self.uk_scale[2]
                * np.exp(-(x[3, ...] * self.uk_scale[3]) * self.b)
                + (1-x[2, ...] * self.uk_scale[2])
                * np.exp(- ADC * self.b)
             )).astype(self.DTYPE)

        S *= self.phase
        S[~np.isfinite(S)] = 0
        return S

    def _execute_gradient_3D(self, x):
        ADC = x[1, ...] * self.uk_scale[1]

        grad_M0 = self.uk_scale[0] * (
            x[2, ...] * self.uk_scale[2]
            * np.exp(- (x[3, ...] * self.uk_scale[3]) * self.b)
            + (1-x[2, ...] * self.uk_scale[2])
            * np.exp(- ADC * self.b))
        # del ADC

        grad_ADC = x[0, ...] * self.uk_scale[0] * (
            - self.b * self.uk_scale[1] * np.exp(- ADC * self.b) + (
                x[2, ...] * self.b * self.uk_scale[2] * self.uk_scale[1] * np.exp(- ADC * self.b)))
        

        grad_f = (x[0, ...] * self.uk_scale[0] * self.uk_scale[2] * (
            np.exp(-(x[3, ...] * self.uk_scale[3]) * self.b)
            - np.exp(- ADC * self.b)))

        grad_ADC_ivim = (
            -x[0, ...] * self.b*self.uk_scale[0] * self.uk_scale[3] * (
                x[2, ...] * self.uk_scale[2] *
                np.exp(- (x[3, ...] * self.uk_scale[3]) * self.b))
            )

        grad = np.array(
            [grad_M0,
             grad_ADC,
             grad_f,
             grad_ADC_ivim], dtype=self.DTYPE)
        grad[~np.isfinite(grad)] = 0
        grad *= self.phase
        return grad

    def plot_unknowns(self, x, dim_2D=False):
        M0 = np.abs(x[0, ...]) * self.uk_scale[0]
        ADC = (np.abs(x[1, ...]) * self.uk_scale[1])
        
        M0_min = M0.min()
        M0_max = M0.max()
        ADC_min = ADC.min()
        ADC_max = ADC.max()

        
        f = np.abs(x[2, ...]) * self.uk_scale[2]
        ADC_ivim = np.abs(x[3, ...]) * self.uk_scale[3]

        f_min = f.min()
        f_max = f.max()
        ADC_ivim_min = ADC_ivim.min()
        ADC_ivim_max = ADC_ivim.max()

        if dim_2D:
            if not self.figure:
                plt.ion()
                self.figure, self.ax = plt.subplots(1, 2, figsize=(12, 5))
                self.M0_plot = self.ax[0].imshow((M0))
                self.ax[0].set_title('Proton Density in a.u.')
                self.ax[0].axis('off')
                self.figure.colorbar(self.M0_plot, ax=self.ax[0])
                self.ADC_plot = self.ax[1].imshow((ADC))
                self.ax[1].set_title('ADC in  ms')
                self.ax[1].axis('off')
                self.figure.colorbar(self.ADC_plot, ax=self.ax[1])
                self.figure.tight_layout()
                plt.draw()
                plt.pause(1e-10)
            else:
                self.M0_plot.set_data((M0))
                self.M0_plot.set_clim([M0_min, M0_max])
                self.ADC_plot.set_data((ADC))
                self.ADC_plot.set_clim([ADC_min, ADC_max])
                plt.draw()
                plt.pause(1e-10)
        else:
            [z, y, x] = M0.shape
            self.ax = []
            self.ax_phase = []
            self.ax_kurt = []
            if not self.figure:
                plt.ion()
                self.figure = plt.figure(figsize=(12, 6))
                self.figure.subplots_adjust(hspace=0, wspace=0)
                self.gs = gridspec.GridSpec(8,
                                            10,
                                            width_ratios=[x / (20 * z),
                                                          x / z,
                                                          1,
                                                          x / z,
                                                          1,
                                                          x / (20 * z),
                                                          x / (2 * z),
                                                          x / z,
                                                          1,
                                                          x / (20 * z)],
                                            height_ratios=[x / z,
                                                           1,
                                                           x / z,
                                                           1,
                                                           x / z,
                                                           1,
                                                           x / z,
                                                           1])
                self.figure.tight_layout()
                self.figure.patch.set_facecolor(plt.cm.viridis.colors[0])
                for grid in self.gs:
                    self.ax.append(plt.subplot(grid))
                    self.ax[-1].axis('off')

                self.M0_plot = self.ax[1].imshow(
                    (M0[int(self.NSlice / 2), ...]))
                self.M0_plot_cor = self.ax[11].imshow(
                    (M0[:, int(M0.shape[1] / 2), ...]))
                self.M0_plot_sag = self.ax[2].imshow(
                    np.flip((M0[:, :, int(M0.shape[-1] / 2)]).T, 1))
                self.ax[1].set_title('Proton Density in a.u.', color='white')
                self.ax[1].set_anchor('SE')
                self.ax[2].set_anchor('SW')
                self.ax[11].set_anchor('NE')
                cax = plt.subplot(self.gs[:2, 0])
                cbar = self.figure.colorbar(self.M0_plot, cax=cax)
                cbar.ax.tick_params(labelsize=12, colors='white')
                cax.yaxis.set_ticks_position('left')
                for spine in cbar.ax.spines:
                    cbar.ax.spines[spine].set_color('white')

                self.ADC_plot = self.ax[3].imshow(
                    (ADC[int(self.NSlice / 2), ...]))
                self.ADC_plot_cor = self.ax[13].imshow(
                    (ADC[:, int(ADC.shape[1] / 2), ...]))
                self.ADC_plot_sag = self.ax[4].imshow(
                    np.flip((ADC[:, :, int(ADC.shape[-1] / 2)]).T, 1))
                self.ax[3].set_title('ADC', color='white')
                self.ax[3].set_anchor('SE')
                self.ax[4].set_anchor('SW')
                self.ax[13].set_anchor('NE')
                cax = plt.subplot(self.gs[:2, 5])
                cbar = self.figure.colorbar(self.ADC_x_plot, cax=cax)
                cbar.ax.tick_params(labelsize=12, colors='white')
                for spine in cbar.ax.spines:
                    cbar.ax.spines[spine].set_color('white')


                self.f_plot = self.ax[21].imshow(
                    (f[int(self.NSlice / 2), ...]))
                self.f_plot_cor = self.ax[31].imshow(
                    (f[:, int(M0.shape[1] / 2), ...]))
                self.f_plot_sag = self.ax[22].imshow(
                    np.flip((f[:, :, int(f.shape[-1] / 2)]).T, 1))
                self.ax[21].set_title('f in a.u.', color='white')
                self.ax[21].set_anchor('SE')
                self.ax[22].set_anchor('SW')
                self.ax[31].set_anchor('NE')
                cax = plt.subplot(self.gs[2:4, 0])
                cbar = self.figure.colorbar(self.f_plot, cax=cax)
                cbar.ax.tick_params(labelsize=12, colors='white')
                cax.yaxis.set_ticks_position('left')
                for spine in cbar.ax.spines:
                    cbar.ax.spines[spine].set_color('white')

                self.ADC_ivim_plot = self.ax[41].imshow(
                    (ADC_ivim[int(self.NSlice / 2), ...]))
                self.ADC_ivim_plot_cor = self.ax[51].imshow(
                    (ADC_ivim[:, int(M0.shape[1] / 2), ...]))
                self.ADC_ivim_plot_sag = self.ax[42].imshow(
                    np.flip((ADC_ivim[:, :, int(M0.shape[-1] / 2)]).T, 1))
                self.ax[41].set_title('ADC IVIM', color='white')
                self.ax[41].set_anchor('SE')
                self.ax[42].set_anchor('SW')
                self.ax[51].set_anchor('NE')
                cax = plt.subplot(self.gs[4:6, 0])
                cbar = self.figure.colorbar(self.ADC_ivim_plot, cax=cax)
                cbar.ax.tick_params(labelsize=12, colors='white')
                cax.yaxis.set_ticks_position('left')
                for spine in cbar.ax.spines:
                    cbar.ax.spines[spine].set_color('white')

                plt.draw()
                plt.pause(1e-10)
                self.figure.canvas.draw_idle()

            else:
                self.M0_plot.set_data((M0[int(self.NSlice / 2), ...]))
                self.M0_plot_cor.set_data((M0[:, int(M0.shape[1] / 2), ...]))
                self.M0_plot_sag.set_data(
                    np.flip((M0[:, :, int(M0.shape[-1] / 2)]).T, 1))
                self.M0_plot.set_clim([M0_min, M0_max])
                self.M0_plot_cor.set_clim([M0_min, M0_max])
                self.M0_plot_sag.set_clim([M0_min, M0_max])

                self.ADC_plot.set_data((ADC[int(self.NSlice / 2), ...]))
                self.ADC_plot_cor.set_data(
                    (ADC[:, int(ADC.shape[1] / 2), ...]))
                self.ADC_plot_sag.set_data(
                    np.flip((ADC[:, :, int(ADC.shape[-1] / 2)]).T, 1))
                self.ADC_plot.set_clim([ADC_min, ADC_max])
                self.ADC_plot_sag.set_clim([ADC_min, ADC_max])
                self.ADC_plot_cor.set_clim([ADC_min, ADC_max])


                self.f_plot.set_data((f[int(self.NSlice / 2), ...]))
                self.f_plot_cor.set_data((f[:, int(f.shape[1] / 2), ...]))
                self.f_plot_sag.set_data(
                    np.flip((f[:, :, int(f.shape[-1] / 2)]).T, 1))
                self.f_plot.set_clim([f_min, f_max])
                self.f_plot_cor.set_clim([f_min, f_max])
                self.f_plot_sag.set_clim([f_min, f_max])

                self.ADC_ivim_plot.set_data(
                    (ADC_ivim[int(self.NSlice / 2), ...]))
                self.ADC_ivim_plot_cor.set_data(
                    (ADC_ivim[:, int(ADC_ivim.shape[1] / 2), ...]))
                self.ADC_ivim_plot_sag.set_data(
                    np.flip((ADC_ivim[:, :, int(ADC_ivim.shape[-1] / 2)]).T, 1))
                self.ADC_ivim_plot.set_clim([ADC_ivim_min, ADC_ivim_max])
                self.ADC_ivim_plot_cor.set_clim([ADC_ivim_min, ADC_ivim_max])
                self.ADC_ivim_plot_sag.set_clim([ADC_ivim_min, ADC_ivim_max])

                self.figure.canvas.draw_idle()

                plt.draw()
                plt.pause(1e-10)

    def computeInitialGuess(self, *args):
        self.phase = np.exp(1j*(np.angle(args[0])-np.angle(args[0][0])))
        if self.b0 is not None:
            test_M0 = self.b0
        else:
            test_M0 = args[0][0]
        ADC = 1 * np.ones(args[0].shape[-3:], dtype=self.DTYPE)
        f = 0.2 * np.ones(args[0].shape[-3:], dtype=self.DTYPE)
        ADC_ivim = 50 * np.ones(args[0].shape[-3:], dtype=self.DTYPE)

        x = np.array(
                [
                    test_M0 / self.uk_scale[0],
                    ADC,
                    f,
                    ADC_ivim],
                dtype=self.DTYPE)
        self.guess = x
