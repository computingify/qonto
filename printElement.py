import os
import time
import pathlib

def process(path):
    
    # Extracting all the contents in the directory corresponding to path
    l_files = os.listdir(path)
    l_files.reverse()
    # Iterating over all the files
    for file in l_files:
    
        # Instantiating the path of the file
        file_path = f'{path}\\{file}'
    
        # Checking whether the given file is a directory or not
        if os.path.isfile(file_path) and '.pdf' == pathlib.Path(file_path).suffix:
            try:
                # Printing the file pertaining to file_path
                os.startfile(file_path, 'print')
                print(f'Printing {file}')
    
                # Sleeping the program for 5 seconds so as to account the
                # steady processing of the print operation.
                time.sleep(5)
            except:
                # Catching if any error occurs and alerting the user
                print(f'ALERT: {file} could not be printed! Please check\
                the associated softwares, or the file type.')
        else:
            print(f'ALERT: {file} is not a file, so can not be printed!')
            
    print('Task finished!')

if __name__ == "__main__":
    process("2022_10")