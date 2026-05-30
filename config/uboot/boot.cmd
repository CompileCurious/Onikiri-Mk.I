# Armbian sun50i-next style boot script adapted for Onikiri Mk.I.
# Keep policy in armbianEnv.txt; keep script logic close to upstream flow.

setenv load_addr "0x45000000"
setenv overlay_error "false"
setenv rootdev "/dev/mmcblk0p1"
setenv verbosity "1"
setenv rootfstype "ext4"
setenv console "both"
setenv docker_optimizations "on"
setenv bootlogo "false"
setenv vendor "allwinner"

if test -z "${devtype}"; then setenv devtype mmc; fi
if test -z "${devnum}"; then setenv devnum 0; fi
if test -z "${prefix}"; then setenv prefix /; fi
if test -z "${fdtdir}"; then setenv fdtdir "${prefix}dtb/${vendor}"; fi

if setexpr subfdt sub ${vendor}/ "" ${fdtfile}; then
	setenv deffdt_file ${subfdt}
fi

setenv deffdt_dir "${prefix}dtb"

if test -e ${devtype} ${devnum} ${prefix}armbianEnv.txt; then
	load ${devtype} ${devnum} ${load_addr} ${prefix}armbianEnv.txt
	env import -t ${load_addr} ${filesize}
fi

if setexpr subfdt sub ${vendor}/ "" ${fdtfile}; then
	setenv fdtfile ${subfdt}
fi

if test -e ${devtype} ${devnum} "${fdtdir}/${fdtfile}"; then
	echo "Load fdt: ${fdtdir}/${fdtfile}"
else
	if test -e ${devtype} ${devnum} "${deffdt_dir}/${fdtfile}"; then
		setenv fdtdir "${deffdt_dir}"
	else
		if test -e ${devtype} ${devnum} "${deffdt_dir}/${vendor}/${deffdt_file}"; then
			setenv fdtdir "${deffdt_dir}/${vendor}"
			setenv fdtfile "${deffdt_file}"
		else
			if test -e ${devtype} ${devnum} "${deffdt_dir}/${deffdt_file}"; then
				setenv fdtdir "${deffdt_dir}"
				setenv fdtfile "${deffdt_file}"
			fi
		fi
	fi
fi

if test "${console}" = "display" || test "${console}" = "both"; then setenv consoleargs "console=ttyS0,115200 console=tty1"; fi
if test "${console}" = "serial"; then setenv consoleargs "console=ttyS0,115200"; fi
if test "${bootlogo}" = "true"; then
	setenv consoleargs "splash plymouth.ignore-serial-consoles ${consoleargs}"
else
	setenv consoleargs "splash=verbose ${consoleargs}"
fi

if test "${devtype}" = "mmc"; then part uuid mmc 0:1 partuuid; fi

setenv bootargs "root=${rootdev} rootwait rootfstype=${rootfstype} ${consoleargs} consoleblank=0 loglevel=${verbosity} ubootpart=${partuuid} usb-storage.quirks=${usbstoragequirks} ${extraargs} ${extraboardargs}"

if test "${docker_optimizations}" = "on"; then setenv bootargs "${bootargs} cgroup_enable=memory"; fi

load ${devtype} ${devnum} ${fdt_addr_r} ${fdtdir}/${fdtfile}
fdt addr ${fdt_addr_r}
fdt resize 65536

for overlay_file in ${overlays}; do
	if load ${devtype} ${devnum} ${load_addr} ${fdtdir}/overlay/${overlay_prefix}-${overlay_file}.dtbo; then
		fdt apply ${load_addr} || setenv overlay_error "true"
	fi
done

for overlay_file in ${user_overlays}; do
	if load ${devtype} ${devnum} ${load_addr} ${prefix}overlay-user/${overlay_file}.dtbo; then
		fdt apply ${load_addr} || setenv overlay_error "true"
	fi
done

if test "${overlay_error}" = "true"; then
	load ${devtype} ${devnum} ${fdt_addr_r} ${fdtdir}/${fdtfile}
fi

load ${devtype} ${devnum} ${ramdisk_addr_r} ${prefix}uInitrd
load ${devtype} ${devnum} ${kernel_addr_r} ${prefix}Image

booti ${kernel_addr_r} ${ramdisk_addr_r} ${fdt_addr_r}
