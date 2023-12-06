#!/usr/bin/python

#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330,
# Boston,  MA 02111-1307  USA
#

import srv6_explicit_path_pb2_grpc
import srv6_explicit_path_pb2
from pyroute2 import IPRoute
from pyroute2 import NFTables
import logging
import time 
import csv

class SRv6ExplicitPathHandler(srv6_explicit_path_pb2_grpc.SRv6ExplicitPathServicer):
  """gRPC request handler"""

  def __init__(self, _iproute, csv_file):
      self.ipr = _iproute
      self.log = logging.getLogger("SRV6-Manager")
      self.maintable  = 254
      self.csv_f = csv_file
      with open(self.csv_f, 'w') as report:
          writer = csv.writer(report, delimiter='|')
          writer.writerow(["Time","Prefix","Segments","Routing-Table","Interface", "Action"])



  def Execute(self, op, request, context):
    self.log.debug("config received:\n%s", request)
    # Let's push the routes
    for path in request.path:
      # Rebuild segments
      segments = []
      for srv6_segment in path.sr_path:
        segments.append(srv6_segment.segment)
        self.log.info("SERVER DEBUG: Segment is %s" %segments)

      self.log.info("SERVER DEGUG: SEGEMENT: %s  ->  DESTINATION: %s" %(segments, path.destination))
      if path.table == 0:
          rtable = self.maintable
      else:
          rtable = path.table
          self.log.info("SERVER DEBUG: SEGMENT is for PAR TABLE!!!!")
      # Add priority
      if op == 'del':
          self.ipr.route(op, dst=path.destination, oif=path.device,
            table=rtable,
            encap={'type':'seg6', 'mode': path.encapmode, 'segs': segments},
            priority=10)
      else:
          self.ipr.route(op, dst=path.destination, oif=path.device,
            table=rtable,
            encap={'type':'seg6', 'mode':path.encapmode, 'segs':segments},
            priority=10)
      with open(self.csv_f, 'a') as report:
          row = [time.time(), str(path.destination), str(segments), rtable, str(path.device), op]
          writer = csv.writer(report, delimiter='|')
          writer.writerow(row)

    # and create the response
    return srv6_explicit_path_pb2.SRv6EPReply(message="OK")

  def Create(self, request, context):
    # Handle Create operation 
    return self.Execute("add", request, context)


  def Remove(self, request, context):
    # Handle Remove operation 
    return self.Execute("del", request, context)

  def Replace(self, request, context):
      return self.Execute("replace", request, context)

