# OMNIC–Spectragryph Data Transfer Guide

## Purpose and scope

This procedure describes how to process an OMNIC spectrum in Spectragryph and save the modified data back into OMNIC's native `.spa` format. It also covers recording and restoring relevant descriptive metadata.

**File workflow:** `.spa` (OMNIC) → `.spc` (Spectragryph export) → `.spa` (OMNIC)

Spectragryph can read the source spectrum, but the return workflow uses the Thermo Galactic GRAMS `.spc` format as an interchange format rather than writing a new `.spa` file directly.

## 1. Preserve the original spectrum and acquisition information

1. Retain an unmodified copy of the original `.spa` file. Perform all processing on a separate working copy.
2. Open the original spectrum in OMNIC.
3. Open **File > Search Information** and record the acquisition details needed for subsequent interpretation, such as laser frequency, interferometer velocity, and detector settings.
4. Save this information separately, for example in a laboratory record or screenshot. Some acquisition fields may not survive export and reimport.

## 2. Process the spectrum in Spectragryph

1. In Spectragryph, select **File > Open** and load the original `.spa` file.
2. Apply the required processing operations, such as baseline correction, smoothing, scaling, or truncation.
3. Review the processed spectrum and confirm that the axes, units, and spectral range are correct.
4. Select **File > Save Data as** (`Ctrl+Shift+S`).
5. Set the output format to **Thermo Galactic GRAMS (`*.spc`)** and save the processed spectrum under a new filename.

The binary `.spc` format is used to transfer the spectral coordinates and basic axis information. It should not be assumed to preserve every acquisition parameter or processing-history field from the original `.spa` file.

## 3. Import the processed spectrum into OMNIC

1. In OMNIC, select **File > Open**.
2. Open the `.spc` file exported from Spectragryph.
3. Confirm that the processed spectrum appears as expected, including the spectral range, axis units, and modified signal.
4. Select the imported spectrum and choose **File > Save As**.
5. Set the file type to **Nicolet Spectrum (`*.spa`)** and save it under a new filename.

This creates an OMNIC-readable `.spa` file containing the processed spectrum. It does not reconstruct instrument-generated acquisition records that were lost during interchange.

## 4. Restore descriptive metadata

1. With the new spectrum active in OMNIC, open the relevant text or spectrum-information editor. Depending on the OMNIC version, this may be available through **Edit > Edit Text**, **Title**, or **File > Window Information**.
2. Enter the descriptive information required for identification and traceability, including relevant sample details, measurement conditions, acquisition settings, and processing notes.
3. Clearly identify values copied from the original acquisition record and describe the processing performed in Spectragryph.
4. Save the `.spa` file again to retain the edits.
5. Reopen the saved file and confirm that the entered information remains available in OMNIC.

**Important:** Do not edit `.spa` files in a plain-text editor. They are binary files and direct text replacement can damage the file.

### Metadata limitations

OMNIC distinguishes between instrument-generated acquisition information and user-editable descriptive fields. User-editable text can document original settings, but it does not restore the original instrument-generated metadata or make the processed file equivalent to the untouched acquisition file.

Availability of editable fields and their behavior in library searches may vary by OMNIC version and configuration. Verify searchability in the local installation if it is required for the workflow.

## 5. Verify the result

Before distributing or archiving the processed file, check that:

- [ ] The original `.spa` file remains unchanged and is archived separately.
- [ ] The processed spectrum opens correctly in OMNIC.
- [ ] The spectral range, axis units, and signal values match the intended Spectragryph output.
- [ ] The new `.spa` file can be closed and reopened successfully.
- [ ] Sample identification, processing notes, and relevant acquisition details are retained in the intended OMNIC fields.
- [ ] The processed file is distinguishable from the original measurement.
