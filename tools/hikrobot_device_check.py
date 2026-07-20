#!/usr/bin/env python3
"""Check Hikrobot MVS SDK and enumerate/test connected cameras.

Usage::

    python tools/hikrobot_device_check.py
    python tools/hikrobot_device_check.py --open  # also open camera and grab test frame
"""

import argparse, ctypes, os, sys

def _setup_paths():
    sys.path.insert(0, '/opt/MVS/Samples/64/Python/MvImport')
    os.environ.setdefault('MVCAM_COMMON_RUNENV', '/opt/MVS/lib')

def enum():
    _setup_paths()
    from MvCameraControl_class import MvCamera, MV_CC_DEVICE_INFO_LIST
    from CameraParams_const import MV_USB_DEVICE, MV_GIGE_DEVICE

    for tlayer, name in [(MV_GIGE_DEVICE, "GigE"), (MV_USB_DEVICE, "USB"), (MV_GIGE_DEVICE | MV_USB_DEVICE, "GigE|USB")]:
        dl = MV_CC_DEVICE_INFO_LIST()
        ret = MvCamera.MV_CC_EnumDevices(tlayer, dl)
        print(f"  {name}: ret=0x{ret:08X}  count={dl.nDeviceNum}")
        if dl.nDeviceNum > 0:
            return True
    return False

def open_test():
    _setup_paths()
    from CameraParams_const import MV_USB_DEVICE, MV_ACCESS_Exclusive
    from MvCameraControl_class import MvCamera, MV_CC_DEVICE_INFO_LIST, MV_CC_DEVICE_INFO, \
        MV_FRAME_OUT_INFO_EX, MVCC_INTVALUE

    dl = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(MV_USB_DEVICE, dl)
    if dl.nDeviceNum == 0:
        print("ERROR: no USB camera")
        return

    dev = ctypes.cast(dl.pDeviceInfo[0], ctypes.POINTER(MV_CC_DEVICE_INFO)).contents
    cam = MvCamera()
    cam.MV_CC_CreateHandle(dev)
    cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
    cam.MV_CC_SetEnumValue("TriggerMode", 0)
    cam.MV_CC_SetEnumValue("ExposureAuto", 0)
    cam.MV_CC_SetEnumValue("GainAuto", 0)
    cam.MV_CC_SetEnumValue("PixelFormat", 0x01080001)
    cam.MV_CC_SetFloatValue("ExposureTime", 5000.0)
    cam.MV_CC_SetFloatValue("Gain", 0.0)

    st = MVCC_INTVALUE()
    ctypes.memset(ctypes.byref(st), 0, ctypes.sizeof(st))
    cam.MV_CC_GetIntValue("PayloadSize", st)
    cam.MV_CC_StartGrabbing()

    import numpy as np
    buf = (ctypes.c_ubyte * st.nCurValue)()
    fi = MV_FRAME_OUT_INFO_EX()
    ctypes.memset(ctypes.byref(fi), 0, ctypes.sizeof(fi))
    cam.MV_CC_GetOneFrameTimeout(buf, st.nCurValue, fi, 3000)
    raw = np.frombuffer(buf, dtype=np.uint8, count=fi.nFrameLen)
    img = raw[:fi.nWidth * fi.nHeight].reshape(fi.nHeight, fi.nWidth)
    print(f"  Resolution: {fi.nWidth}x{fi.nHeight}")
    print(f"  PixelFormat: Mono8")
    print(f"  Brightness: min={img.min()} max={img.max()} mean={img.mean():.1f}")

    cam.MV_CC_StopGrabbing()
    cam.MV_CC_CloseDevice()
    cam.MV_CC_DestroyHandle()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--open', action='store_true', help='Open camera and grab test frame')
    args = p.parse_args()

    print("=== Hikrobot Device Check ===")
    print("Enumeration:")
    found = enum()
    if not found:
        print("  WARNING: no cameras found!")
        sys.exit(1)

    if args.open:
        print("Open test:")
        open_test()
