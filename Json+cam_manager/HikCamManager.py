from imswitch.imcommon.model import initLogger

from .DetectorManager import (
    DetectorAction,
    DetectorBooleanParameter,
    DetectorListParameter,
    DetectorManager,
    DetectorNumberParameter,
)


class HikCamManager(DetectorManager):
    """DetectorManager that deals with HIK Vision cameras and the
    parameters for frame extraction from them.

    Manager properties:

    - ``cameraListIndex`` -- the camera's index in the Hik Vision camera list (list
      indexing starts at 0); set this string to an invalid value, e.g. the
      string "mock" to load a mocker
    - ``hikcam`` -- dictionary of Hik Vision camera properties
    """

    def __init__(self, detectorInfo, name, **_lowLevelManagers):
        self.__logger = initLogger(self, instanceName=name)
        self.detectorInfo = detectorInfo

        binning = 1
        cameraId = detectorInfo.managerProperties["cameraListIndex"]
        try:
            pixelSize = detectorInfo.managerProperties["cameraEffPixelsize"]  # µm
        except:
            pixelSize = 1

        try:
            self._mockstackpath = detectorInfo.managerProperties["mockstackpath"]
        except:
            self._mockstackpath = None

        try:  # FIXME: get that from the real camera
            isRGB = detectorInfo.managerProperties["isRGB"]
        except:
            isRGB = False

        try:
            self._mocktype = detectorInfo.managerProperties["mocktype"]
        except:
            self._mocktype = "normal"

        # Initialize camera
        self._camera = self._getHikObj(cameraId, isRGB, binning)

        # Set camera properties if hikcam section exists
        if "hikcam" in detectorInfo.managerProperties:
            for propertyName, propertyValue in detectorInfo.managerProperties["hikcam"].items():
                try:
                    self._camera.setPropertyValue(propertyName, propertyValue)
                except Exception as e:
                    self.__logger.warning(f"Failed to set property {propertyName}: {e}")

        # Get camera dimensions - handle potential zero values
        sensor_width = self._camera.SensorWidth if self._camera.SensorWidth > 0 else 1024
        sensor_height = self._camera.SensorHeight if self._camera.SensorHeight > 0 else 1024

        fullShape = (sensor_width, sensor_height)

        model = self._camera.model
        self._running = False
        self._adjustingParameters = False

        # TODO: Not implemented yet
        self.crop(hpos=0, vpos=0, hsize=fullShape[0], vsize=fullShape[1])

        # Prepare parameters - get initial values from camera where possible
        try:
            initial_exposure = self._camera.getPropertyValue("exposure")
        except:
            initial_exposure = 100

        try:
            initial_gain = self._camera.getPropertyValue("gain")
        except:
            initial_gain = 1

        try:
            initial_blacklevel = self._camera.getPropertyValue("blacklevel")
        except:
            initial_blacklevel = 100

        parameters = {
            "exposure": DetectorNumberParameter(
                group="Misc", value=initial_exposure, valueUnits="ms", editable=True
            ),
            "gain": DetectorNumberParameter(
                group="Misc", value=initial_gain, valueUnits="arb.u.", editable=True
            ),
            "blacklevel": DetectorNumberParameter(
                group="Misc", value=initial_blacklevel, valueUnits="arb.u.", editable=True
            ),
            "image_width": DetectorNumberParameter(
                group="Misc", value=fullShape[0], valueUnits="pixels", editable=False
            ),
            "image_height": DetectorNumberParameter(
                group="Misc", value=fullShape[1], valueUnits="pixels", editable=False
            ),
            "frame_rate": DetectorNumberParameter(
                group="Misc", value=-1, valueUnits="fps", editable=True
            ),
            "frame_number": DetectorNumberParameter(
                group="Misc", value=1, valueUnits="frames", editable=False
            ),
            "exposure_mode": DetectorListParameter(
                group="Misc", value="manual", options=["manual", "auto", "once"], editable=True
            ),
            "flat_fielding": DetectorBooleanParameter(group="Misc", value=False, editable=True),
            "mode": DetectorListParameter(
                group="Misc", value="manual", options=["manual", "auto"], editable=True
            ),
            "previewMinValue": DetectorNumberParameter(
                group="Misc", value=0, valueUnits="arb.u.", editable=True
            ),
            "previewMaxValue": DetectorNumberParameter(
                group="Misc", value=255, valueUnits="arb.u.", editable=True
            ),
            "trigger_source": DetectorListParameter(
                group="Acquisition mode",
                value="Continous",
                options=["Continous", "Internal trigger", "External trigger"],
                editable=True,
            ),
            "Camera pixel size": DetectorNumberParameter(
                group="Miscellaneous", value=pixelSize, valueUnits="µm", editable=True
            ),
        }

        # Prepare actions
        actions = {
            "More properties": DetectorAction(group="Misc", func=self._camera.openPropertiesGUI)
        }

        super().__init__(
            detectorInfo,
            name,
            fullShape=fullShape,
            supportedBinnings=[1],
            model=model,
            parameters=parameters,
            actions=actions,
            croppable=True,
        )

    def setFlatfieldImage(self, flatfieldImage, isFlatfielding):
        self._camera.setFlatfieldImage(flatfieldImage, isFlatfielding)

    def getLatestFrame(self, is_resize=True, returnFrameNumber=False):
        return self._camera.getLast(returnFrameNumber=returnFrameNumber)

    def setParameter(self, name, value):
        """Sets a parameter value and returns the value.
        If the parameter doesn't exist, i.e. the parameters field doesn't
        contain a key with the specified parameter name, an error will be
        raised."""

        super().setParameter(name, value)

        if name not in self._DetectorManager__parameters:
            raise AttributeError(f'Non-existent parameter "{name}" specified')

        try:
            value = self._camera.setPropertyValue(name, value)
        except Exception as e:
            self.__logger.warning(f"Failed to set camera property {name}: {e}")

        return value

    def getParameter(self, name):
        """Gets a parameter value and returns the value.
        If the parameter doesn't exist, i.e. the parameters field doesn't
        contain a key with the specified parameter name, an error will be
        raised."""

        if name not in self._parameters:
            raise AttributeError(f'Non-existent parameter "{name}" specified')

        try:
            value = self._camera.getPropertyValue(name)
        except Exception as e:
            self.__logger.warning(f"Failed to get camera property {name}: {e}")
            # Fallback to parameter value
            value = self._parameters[name].value

        return value

    def setTriggerSource(self, source):
        # update camera safely and mirror value in GUI parameter list
        self._performSafeCameraAction(lambda: self._camera.setTriggerSource(source))
        self.parameters["trigger_source"].value = source

    def getChunk(self):
        try:
            return self._camera.getLastChunk()
        except:
            return None

    def flushBuffers(self):
        self._camera.flushBuffer()

    def startAcquisition(self):
        if self._camera.model == "mock":
            self.__logger.debug("Mock camera - attempting to start acquisition")

        if not self._running:
            try:
                self._camera.start_live()
                self._running = True
                self.__logger.debug("Started live acquisition")
            except Exception as e:
                self.__logger.error(f"Failed to start acquisition: {e}")

    def stopAcquisition(self):
        if self._running:
            try:
                self._running = False
                self._camera.suspend_live()
                self.__logger.debug("Suspended live acquisition")
            except Exception as e:
                self.__logger.error(f"Failed to stop acquisition: {e}")

    def stopAcquisitionForROIChange(self):
        if self._running:
            try:
                self._running = False
                self._camera.stop_live()
                self.__logger.debug("Stopped acquisition for ROI change")
            except Exception as e:
                self.__logger.error(f"Failed to stop acquisition for ROI change: {e}")

    def finalize(self) -> None:
        super().finalize()
        self.__logger.debug("Safely disconnecting the camera...")
        try:
            self._camera.close()
        except Exception as e:
            self.__logger.error(f"Error during camera finalization: {e}")

    @property
    def pixelSizeUm(self):
        umxpx = self.parameters["Camera pixel size"].value
        return [1, umxpx, umxpx]

    def setPixelSizeUm(self, pixelSizeUm):
        self.parameters["Camera pixel size"].value = pixelSizeUm

    def crop(self, hpos, vpos, hsize, vsize):
        # TODO: Implement ROI functionality
        pass

    def _performSafeCameraAction(self, function):
        """This method is used to change those camera properties that need
        the camera to be idle to be able to be adjusted.
        """
        self._adjustingParameters = True
        wasrunning = self._running
        if wasrunning:
            self.stopAcquisitionForROIChange()

        try:
            function()
        except Exception as e:
            self.__logger.error(f"Error during safe camera action: {e}")

        if wasrunning:
            self.startAcquisition()
        self._adjustingParameters = False

    def openPropertiesDialog(self):
        try:
            self._camera.openPropertiesGUI()
        except Exception as e:
            self.__logger.warning(f"Properties dialog not available: {e}")

    def _getHikObj(self, cameraId, isRGB=False, binning=1):
        try:
            from imswitch.imcontrol.model.interfaces.hikcamera import CameraHIK

            self.__logger.debug(f"Trying to initialize HIK camera {cameraId}")
            camera = CameraHIK(cameraNo=cameraId, isRGB=isRGB, binning=binning)
        except Exception as e:
            self.__logger.error(f"Failed to initialize HIK camera: {e}")
            self.__logger.warning(f"Failed to initialize CameraHIK {cameraId}, loading TIS mocker")
            try:
                from imswitch.imcontrol.model.interfaces.tiscamera_mock import MockCameraTIS

                camera = MockCameraTIS(
                    mocktype=self._mocktype, mockstackpath=self._mockstackpath, isRGB=isRGB
                )
            except Exception as mock_error:
                self.__logger.error(f"Failed to load mock camera: {mock_error}")
                raise Exception(
                    f"Failed to initialize both real and mock camera: {e}, {mock_error}"
                )

        self.__logger.info(f"Initialized camera, model: {camera.model}")
        return camera

    def closeEvent(self):
        try:
            self._camera.close()
        except Exception as e:
            self.__logger.error(f"Error during camera close: {e}")

    def recordFlatfieldImage(self):
        """
        Record n images and average them before subtracting from the latest frame
        """
        try:
            self._camera.recordFlatfieldImage()
        except Exception as e:
            self.__logger.error(f"Failed to record flatfield image: {e}")

    def getExposure(self):
        """Required abstract method from DetectorManager"""
        try:
            return self._camera.getPropertyValue("exposure")
        except Exception as e:
            self.__logger.warning(f"Failed to get exposure: {e}")
            return self.parameters["exposure"].value

    def setExposure(self, exposure):
        """Set exposure time"""
        try:
            self._camera.setPropertyValue("exposure", exposure)
            self.parameters["exposure"].value = exposure
        except Exception as e:
            self.__logger.warning(f"Failed to set exposure: {e}")

    def getGain(self):
        """Get current gain value"""
        try:
            return self._camera.getPropertyValue("gain")
        except Exception as e:
            self.__logger.warning(f"Failed to get gain: {e}")
            return self.parameters["gain"].value

    def setGain(self, gain):
        """Set gain value"""
        try:
            self._camera.setPropertyValue("gain", gain)
            self.parameters["gain"].value = gain
        except Exception as e:
            self.__logger.warning(f"Failed to set gain: {e}")

    def checkGigEPerformance(self):
        """Check GigE camera performance statistics"""
        try:
            self._camera.check_gige_statistics()
        except Exception as e:
            self.__logger.warning(f"Could not check GigE performance: {e}")


# Copyright (C) ImSwitch developers 2021
# This file is part of ImSwitch.
#
# ImSwitch is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ImSwitch is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
