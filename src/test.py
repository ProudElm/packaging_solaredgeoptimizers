#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      Job
#
# Created:     14-11-2022
# Copyright:   (c) Job 2022
# Licence:     <your licence>
#-------------------------------------------------------------------------------
#from solaredgeoptimizers import solaredgeoptimizers
import sys
import os

#SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
#sys.path.append(os.path.dirname(SCRIPT_DIR))

from solaredgeoptimizers import solaredgeoptimizers

def main():
    siteId = "1871534"
    username = "job_sande@yahoo.co.uk"
    password = "Fckgwrhqq@2"

    api = solaredgeoptimizers(siteId, username, password)

    if api.check_login():

        alles = api.requestAllData()

        #wtf = api.getLifeTimeEnergy()
        #print(wtf)
        for paneel in alles:
            print(paneel.lifetime_energy)

        #panelen = api.requestListOfAllPanels().ReturnAllPanelsIds()

        #for paneel in panelen:
#            data = api.requestSystemData(paneel.split('|')[0])

#            datum = data.lastmeasurement

 #           print(datum)

  #          exit()



if __name__ == '__main__':
    main()
