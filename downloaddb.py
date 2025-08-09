import gdown
# Make sure gdown is installed (first time only)


# Download the SQLite file using gdown
file_id = "1M3ijJIWDEGqGOw4Prx2AXFhts2cv-J1d"
output_file = "sessionresults.db"  # or whatever filename you want

gdown.download(id=file_id, output=output_file, quiet=False)
