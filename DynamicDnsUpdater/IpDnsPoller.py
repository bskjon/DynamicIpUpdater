import datetime
import logging
import random
from threading import Thread
import threading
import traceback
import queue
from typing import List
import os, sys, time, errno

from DynamicDnsUpdater.Dns.Registry import Registry
from DynamicDnsUpdater.Dns.Resolve import Resolve
from .objects import IpData, Auth, DDNSEntry
from .Ip.NetworkAdapter import NetworkAdapter
from util import get_domain_from_fqdn

logging.basicConfig(level=logging.INFO)

iteration_delay = 5

class IpDnsPoller:
    stopFlag = threading.Event()
    watchers: List[Thread] = []
    stopFlag = threading.Event()

    ddnsEntries: List[DDNSEntry] = []
    auth: Auth

    resolve = Resolve()


    def __init__(self, auth: Auth, ddnsEntries: List[DDNSEntry]) -> None:
        self.auth = auth
        for entry in ddnsEntries:
            self.watchers.append(Thread(target=self.__monitor, kwargs={'entry': entry}))
        pass

    def start(self) -> None:
        for thread in self.watchers:
            thread.start()

    def stop(self) -> None:
        self.stopFlag.set()

    def __monitor(self, entry: DDNSEntry) -> None:
        while not self.stopFlag.is_set():
            adapter: NetworkAdapter = NetworkAdapter(entry.interface)
            ipdata = adapter.getIpData()
            if (ipdata.isValid()):
                self.__validateDnsRecordAgainstIpReceivedAndUpdate(entry.interface, ipdata)
        iterationLock = time.time() + datetime.timedelta(minutes=iteration_delay).seconds
        logging.info("Next automatic check will occur @ {}".format(datetime.datetime.fromtimestamp(iterationLock).strftime("%d.%m.%Y %H:%M")))
        time.sleep(60*iteration_delay)
            

    def __validateDnsRecordAgainstIpReceivedAndUpdate(self, nic: str, ipdata: IpData) -> None:
        ddnsEntry = next(filter(lambda entry: entry.interface == nic, self.ddnsEntries))
        if (ddnsEntry.ipv4 == True):
            invalidPointers = self.__find_invalid_pointer4(ddnsEntry.domains)
            for invalidPointer in invalidPointers:
                domain = get_domain_from_fqdn(invalidPointer)
                registry = Registry(domain=domain, auth=self.auth)
                record = registry.build_record(fqdn=domain, ip=ipdata.ip)
                logging.info(f"Preparing record for top domain {domain} and FQDN {invalidPointer}\n\t -> {record}")
                registry.update_record(invalidPointer, record)
        if (ddnsEntry.ipv6 == True):
            invalidPointers = self.__find_invalid_pointer6(ddnsEntry.domains)
            for invalidPointer in invalidPointers:
                domain = get_domain_from_fqdn(invalidPointer)
                registry = Registry(domain=domain, auth=self.auth)
                record = registry.build_record(fqdn=domain, ip=ipdata.ipv6)
                logging.info(f"Preparing record for top domain {domain} and FQDN {invalidPointer}\n\t -> {record}")
                registry.update_record(invalidPointer, record)

    def __find_invalid_pointer4(self, ip: str, domains: List[str]) -> List[str]:
        invalids: List[str] = []
        for domain in domains:
            result = self.resolve.lookup4(domain)
            if (result.ip != ip):
                invalids.append(domain)
        return invalids
    
    def __find_invalid_pointer6(self, ip: str, domains: List[str]) -> List[str]:
        invalids: List[str] = []
        for domain in domains:
            result = self.resolve.lookup6(domain)
            if (result.ip != ip):
                invalids.append(domain)
        return invalids