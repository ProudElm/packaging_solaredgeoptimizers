""" My module """
import requests
import json
import logging
import pytz

from requests import Session
from datetime import datetime, timedelta
from jsonfinder import jsonfinder

class solaredgeoptimizers:
    def __init__(self, siteid, username, password):
        self.siteid = siteid
        self.username = username
        self.password = password

    def check_login(self):
        url = "https://monitoring.solaredge.com/solaredge-apigw/api/sites/{}/layout/logical".format(
            self.siteid
        )

        kwargs = {}
        kwargs["auth"] = requests.auth.HTTPBasicAuth(self.username, self.password)
        r = requests.get(url, **kwargs)

        return r.status_code

    def requestLogicalLayout(self):
        url = "https://monitoring.solaredge.com/solaredge-apigw/api/sites/{}/layout/logical".format(
            self.siteid
        )

        kwargs = {}

        kwargs["auth"] = requests.auth.HTTPBasicAuth(self.username, self.password)
        r = requests.get(url, **kwargs)

        return r.text

    def requestListOfAllPanels(self):
        json_obj = json.loads(self.requestLogicalLayout())
        return SolarEdgeSite(json_obj)

    def requestSystemData(self, itemId):
        url = "https://monitoringpublic.solaredge.com/solaredge-web/p/publicSystemData?reporterId={}&type=panel&activeTab=0&fieldId={}&isPublic=true&locale=en_US".format(
            itemId, self.siteid
        )

        kwargs = {}
        kwargs["auth"] = requests.auth.HTTPBasicAuth(self.username, self.password)
        r = requests.get(url, **kwargs)

        if r.status_code == 200:
            json_object = self.decodeResult(r.text)
            try:
                if json_object["lastMeasurementDate"] == "":
                    print("Skipping optimizer %s without measurements", itemId)
                    return None
                else:
                    return SolarEdgeOptimizerData(itemId, json_object)
            except Exception as e:
                print("Error while processing data")
                print(e)
                raise Exception("Error while processing data") from e
        else:
            print("Error with sending request. Status code: {}".format(r.status_code))
            print(r.text)
            raise Exception("Problem sending request, status code %d: %s" % (r.status_code, r.text))

    def requestAllData(self):

        solarsite = self.requestListOfAllPanels()

        lifetimeenergy = json.loads(self.getLifeTimeEnergy())

        data = []
        for inverter in solarsite.inverters:
            for string in inverter.strings:
                for optimizer in string.optimizers:
                    info = self.requestSystemData(optimizer.optimizerId)
                    if info is not None:
                        # Life time energy adding
                        info.lifetime_energy = (float(lifetimeenergy[str(optimizer.optimizerId)]["unscaledEnergy"])) / 1000

                        data.append(info)

        return data

    def requestItemHistory(self, itemId, starttime=None, endtime=None, parameter="Power"):
        """
        Request measurement history of a panel given a time window defined by start- and endtime
        :param itemId: itemId of the item (panel, string, inverter)
        :param starttime: starttime as datetime or unix timestamp in ms, or None for start of today
        :param endtime: endtime as datetime or unix timestamp in ms, or None for 24 hour after starttime
        :param parameter: the measurement parameter to return
            a list of available parameters can be obtained using: https://monitoring.solaredge.com/solaredge-web/p/chartParamsList?fieldId={}reporterId={}&format=form
        :return: dictionary with datetime (keys), value (values) pairs
            Note, time resolution of the result depends on the time range spanned by start- and endtime
        """
        if starttime is None:
            now = datetime.now()
            starttime = datetime(now.year, now.month, now.day)
        if isinstance(starttime, datetime):
            starttime = int(starttime.timestamp() * 1000)
        if endtime is None:
            endtime = int(starttime + timedelta(days=1).total_seconds() * 1000)
        if isinstance(endtime, datetime):
            endtime = int(endtime.timestamp() * 1000)

        url = 'https://monitoring.solaredge.com/solaredge-web/p/chartData?reporterId={}&fieldId={}&reporterType=&startDate={:d}&endDate={:d}&uom=W&parameterName={}'.format(
            itemId, self.siteid,
            starttime, endtime, parameter
        )

        r = self._doRequest("GET", url)
        if r.startswith("ERROR001"):
            raise Exception("Error while doing request: %s" % r)

        json_object = self.decodeResult(r)
        try:
            # Note: the timestamp provided by SolarEdge is not a pure POSIX timestamp, but in fact contains a timezone offset.
            return {datetime.utcfromtimestamp(pair['date']/1000).astimezone(pytz.utc): pair['value'] for pair in json_object['dateValuePairs']}
        except Exception as e:
            raise Exception("Error while processing data") from e

    def requestPanelHistory(self, itemId, starttime=None, endtime=None, parameter="Power"):
        assert parameter in ("Power", "Current", "Voltage", "Energy", "PowerBox Voltage")
        return self.requestItemHistory(itemId, starttime=starttime, endtime=endtime, parameter=parameter)

    def requestStringHistory(self, itemId, starttime=None, endtime=None, parameter="Power"):
        assert parameter in ("Energy", "Power")
        return self.requestItemHistory(itemId, starttime=starttime, endtime=endtime, parameter=parameter)

    def requestInverterHistory(self, itemId, starttime=None, endtime=None, parameter="Power"):
        # https://monitoring.solaredge.com/solaredge-web/p/chartParamsList?fieldId={}reporterId={}&format=form
        assert parameter in ("AC Energy",
                             "AC Frequency", "AC Frequency P2", "AC Frequency P3",
                             "AC Voltage", "AC Voltage P2", "AC Voltage P3",
                             "AC Current", "AC Current P2", "AC Current P3",
                             "Power", "DC Voltage", "Purchased back feed AC Energy", "Total Reactive Power", "Power Factor")
        return self.requestItemHistory(itemId, starttime=starttime, endtime=endtime, parameter=parameter)

    def requestHistoricalData(self, starttime=None, endtime=None, type="optimizer", parameter="Power"):
        assert type in ("optimizer", "inverter", "string")

        solarsite = self.requestListOfAllPanels()

        data = {}
        for inverter in solarsite.inverters:
            if "inverter" in type:
                info = self.requestInverterHistory(inverter.inverterId, starttime, endtime, parameter)
                data[inverter] = info
            for string in inverter.strings:
                if "string" in type:
                    info = self.requestStringHistory(string.stringId, starttime, endtime, parameter)
                    data[string] = info
                for optimizer in string.optimizers:
                    if "optimizer" in type:
                        info = self.requestPanelHistory(optimizer.optimizerId, starttime, endtime, parameter)
                        data[optimizer] = info

        return data

    def _doRequest(self, method, request_url, data=None):
        session = Session()
        session.head(
            "https://monitoring.solaredge.com/solaredge-apigw/api/sites/{}/layout/energy".format(
                self.siteid
            )
        )

        url = "https://monitoring.solaredge.com/solaredge-web/p/login"

        session.auth = (self.username, self.password)

        # request a login url the get the correct cookie
        r1 = session.get(url)

        # Fix the cookie to get a string.
        therightcookie = self.MakeStringFromCookie(session.cookies.get_dict())
        # The csrf-token is needed as a seperate header.
        thecrsftoken = self.GetThecsrfToken(session.cookies.get_dict())

        # Build up the request.
        response = session.request(
            method=method,
            url=request_url,
            headers={
                "authority": "monitoring.solaredge.com",
                "accept": "*/*",
                "accept-language": "en-US,en;q=0.9,nl;q=0.8",
                "content-type": "application/json",
                "cookie": therightcookie,
                "origin": "https://monitoring.solaredge.com",
                "referer": "https://monitoring.solaredge.com/solaredge-web/p/site/{}/".format(
                    self.siteid
                ),
                "sec-ch-ua": '"Google Chrome";v="105", "Not)A;Brand";v="8", "Chromium";v="105"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
                "x-csrf-token": thecrsftoken,
                "x-kl-ajax-request": "Ajax_Request",
                "x-requested-with": "XMLHttpRequest",
            },
            data=data
        )

        if response.status_code == 200:
            return response.text
        else:
            return "ERROR001 - HTTP CODE: {}".format(response.status_code)

    def getLifeTimeEnergy(self):
        url = "https://monitoring.solaredge.com/solaredge-apigw/api/sites/{}/layout/energy?timeUnit=ALL".format(
            self.siteid
        )
        return self._doRequest("POST", url)

    def getAlerts(self, only_open=False):
        # Note: this might require FULL_ACCESS rights in the SE portal, as opposed to DASHBOARD_AND_LAYOUT
        url = "https://monitoring.solaredge.com/solaredge-apigw/api/rna/v1.0/site/{}/alerts".format(
            self.siteid
        )
        data = None
        if only_open:
            data = [{"fieldFilterOperator": "IN",
                     "fieldName": "status",
                     "fieldValue": ["OPEN"]}]
        return self._doRequest("POST", url, data=json.dumps(data))

    def GetThecsrfToken(self, cookies):
        for cookie in cookies:
            if cookie == "CSRF-TOKEN":
                return cookies[cookie]

    def MakeStringFromCookie(self, cookies):

        maincookiestring = ""
        for cookie in cookies:
            if cookie == "CSRF-TOKEN":
                maincookiestring = (
                    maincookiestring + cookie + "=" + cookies[cookie] + ";"
                )
            elif cookie == "JSESSIONID":
                maincookiestring = (
                    maincookiestring + cookie + "=" + cookies[cookie] + ";"
                )

        maincookiestring = (
            maincookiestring
            + "SolarEdge_Locale=nl_NL; SolarEdge_Locale=nl_NL; solaredge_cookie_concent=1;SolarEdge_Field_ID={}".format(
                self.siteid
            )
        )

        return maincookiestring

    def decodeResult(self, result):
        json_result = ""
        for _, __, obj in jsonfinder(result, json_only=True):
            json_result = obj
            break
        else:
            raise ValueError("data not found")

        return json_result

class SolarEdgeSite:
    def __init__(self, json_obj):
        self.siteId = json_obj["siteId"]
        self.inverters = self.__GetAllInverters(json_obj)

    def __GetAllInverters(self, json_obj):

        inverters = []
        for i in range(len(json_obj["logicalTree"]["childIds"])):

            # Blijkbaar kan er een powermeter tussen zitten. Checken of dit het geval is
            # Production Meter -> moeten 1 niveau dieper
            # Inverter 1 -> dit is 'normaal'
            if "PRODUCTION METER" not in json_obj["logicalTree"]["children"][i]["data"]["name"].upper():
                inverters.append(SolarEdgeInverter(json_obj=json_obj, index=i))
            else:
                for j in range(len(json_obj["logicalTree"]["children"][i]["childIds"])):
                    #inverters.append(SolarEdgeInverter(json_obj, i, j, True))
                    inverters.append(SolarEdgeInverter(json_obj=json_obj, index=i, index2=j, powermeterpresent=True))

        return inverters

    def returnNumberOfOptimizers(self):
        i = 0

        for inverter in self.inverters:
            for string in inverter.strings:
                i = i + len(string.optimizers)

        return i

    def ReturnAllPanelsIds(self):

        panel_ids = []

        for inverter in self.inverters:
            for string in inverter.strings:
                for optimizer in string.optimizers:
                    panel_ids.append(
                        "{}|{}".format(optimizer.optimizerId, optimizer.serialNumber)
                    )

        return panel_ids


class SolarEdgeInverter:

    def __init__(self, json_obj, index, index2=0, powermeterpresent=False):
        if powermeterpresent:
            self.inverterId = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["id"]
            self.serialNumber = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["serialNumber"]
            self.name = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["name"]
            self.displayName = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["displayName"]
            self.relativeOrder = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["relativeOrder"]
            self.type = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["type"]
            self.operationsKey = json_obj["logicalTree"]["children"][index]["children"][index2]["data"]["operationsKey"]

            self.strings = self.__GetStringInformation(json_obj["logicalTree"]["children"][index]["children"][index2]["children"], index2)
        else:
            self.inverterId = json_obj["logicalTree"]["children"][index]["data"]["id"]
            self.serialNumber = json_obj["logicalTree"]["children"][index]["data"]["serialNumber"]
            self.name = json_obj["logicalTree"]["children"][index]["data"]["name"]
            self.displayName = json_obj["logicalTree"]["children"][index]["data"]["displayName"]
            self.relativeOrder = json_obj["logicalTree"]["children"][index]["data"]["relativeOrder"]
            self.type = json_obj["logicalTree"]["children"][index]["data"]["type"]
            self.operationsKey = json_obj["logicalTree"]["children"][index]["data"]["operationsKey"]

            self.strings = self.__GetStringInformation(json_obj["logicalTree"]["children"][index]["children"], index)


    def __GetStringInformation(self, json_obj, index):
        strings = []

        for i in range(len(json_obj)):
            if "STRING" in json_obj[i]["data"]["name"].upper():
                strings.append(SolarEdgeString(json_obj[i]))
            else:
                for j in range(len(json_obj[i]["children"])):
                    strings.append(SolarEdgeString(json_obj[i]["children"][j]))

        return strings


class SolarEdgeString:
    def __init__(self, json_obj):
        self.stringId = json_obj["data"]["id"]
        self.serialNumber = json_obj["data"]["serialNumber"]
        self.name = json_obj["data"]["name"]
        self.displayName = json_obj["data"]["displayName"]
        self.relativeOrder = json_obj["data"]["relativeOrder"]
        self.type = json_obj["data"]["type"]
        self.operationsKey = json_obj["data"]["operationsKey"]
        self.optimizers = self.__GetOptimizers(json_obj)

    def __GetOptimizers(self, json_obj):
        optimizers = []

        for i in range(len(json_obj["children"])):
            optimizers.append(SolarlEdgeOptimizer(json_obj["children"][i]))

        return optimizers


class SolarlEdgeOptimizer:
    def __init__(self, json_obj):
        self.optimizerId = json_obj["data"]["id"]
        self.serialNumber = json_obj["data"]["serialNumber"]
        self.name = json_obj["data"]["name"]
        self.displayName = json_obj["data"]["displayName"]
        self.relativeOrder = json_obj["data"]["relativeOrder"]
        self.type = json_obj["data"]["type"]
        self.operationsKey = json_obj["data"]["operationsKey"]


class SolarEdgeOptimizerData:
    """boe"""

    def __init__(self, paneelid, json_object):

        # Atributen die we willen zien:
        self.serialnumber = ""
        self.paneel_id = ""
        self.paneel_desciption = ""
        self.lastmeasurement = ""
        self.model = ""
        self.manufacturer = ""

        # Waarden
        self.current = ""
        self.optimizer_voltage = ""
        self.power = ""
        self.voltage = ""

        # Extra info
        self.lifetime_energy = ""

        if paneelid is not None:
            self._json_obj = json_object

            # Atributen die we willen zien:
            self.serialnumber = json_object["serialNumber"]
            self.paneel_id = paneelid
            self.paneel_desciption = json_object["description"]
            rawdate = json_object["lastMeasurementDate"]

            # Removing the Timezone information
            new_time = "{} {} {} {} {}".format(
                rawdate.split(' ')[0],rawdate.split(' ')[1],rawdate.split(' ')[2],
                rawdate.split(' ')[3],rawdate.split(' ')[5]
            )
            self.lastmeasurement = datetime.strptime(new_time, "%a %b %d %H:%M:%S %Y")

            self.model = json_object["model"]
            self.manufacturer = json_object["manufacturer"]

            # Waarden
            self.current = json_object["measurements"]["Current [A]"]
            self.optimizer_voltage = json_object["measurements"][
                "Optimizer Voltage [V]"
            ]
            self.power = json_object["measurements"]["Power [W]"]
            self.voltage = json_object["measurements"]["Voltage [V]"]
