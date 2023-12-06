# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: dataplaneapi.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2
import dataplane_pb2 as dataplane__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='dataplaneapi.proto',
  package='',
  syntax='proto3',
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\x12\x64\x61taplaneapi.proto\x1a\x1bgoogle/protobuf/empty.proto\x1a\x0f\x64\x61taplane.proto2\xf7\x03\n\x0e\x44\x61taplaneState\x12\x44\n\tGetIfaces\x12\x16.google.protobuf.Empty\x1a\x1d.DataplaneService.ReplyIfaces\"\x00\x12U\n\x11GetExternalIfaces\x12\x1f.DataplaneService.RequestIfaces\x1a\x1d.DataplaneService.ReplyIfaces\"\x00\x12U\n\x11GetInternalIfaces\x12\x1f.DataplaneService.RequestIfaces\x1a\x1d.DataplaneService.ReplyIfaces\"\x00\x12Q\n\x10GetRoutingTables\x12\x16.google.protobuf.Empty\x1a#.DataplaneService.RoutesInAllTables\"\x00\x12M\n\rGetRouteTable\x12\x19.DataplaneService.RTables\x1a\x1f.DataplaneService.RoutesInTable\"\x00\x12O\n\x0cGetip6tables\x12\x16.google.protobuf.Empty\x1a%.DataplaneService.RequestIP6TableRule\"\x00\x32\x9a\x02\n\x12\x43onfigureDataplane\x12P\n\x08\x46lowMark\x12!.DataplaneService.RequestFlowMark\x1a\x1f.DataplaneService.ReplyFlowMark\"\x00\x12Q\n\x10\x43reateRouteTable\x12\x1a.DataplaneService.PARFlows\x1a\x1f.DataplaneService.ReplyPARFlows\"\x00\x12_\n\x0f\x41\x64\x64Ip6tableRule\x12%.DataplaneService.RequestIP6TableRule\x1a#.DataplaneService.ReplyIP6TableRule\"\x00\x62\x06proto3'
  ,
  dependencies=[google_dot_protobuf_dot_empty__pb2.DESCRIPTOR,dataplane__pb2.DESCRIPTOR,])



_sym_db.RegisterFileDescriptor(DESCRIPTOR)



_DATAPLANESTATE = _descriptor.ServiceDescriptor(
  name='DataplaneState',
  full_name='DataplaneState',
  file=DESCRIPTOR,
  index=0,
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_start=69,
  serialized_end=572,
  methods=[
  _descriptor.MethodDescriptor(
    name='GetIfaces',
    full_name='DataplaneState.GetIfaces',
    index=0,
    containing_service=None,
    input_type=google_dot_protobuf_dot_empty__pb2._EMPTY,
    output_type=dataplane__pb2._REPLYIFACES,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='GetExternalIfaces',
    full_name='DataplaneState.GetExternalIfaces',
    index=1,
    containing_service=None,
    input_type=dataplane__pb2._REQUESTIFACES,
    output_type=dataplane__pb2._REPLYIFACES,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='GetInternalIfaces',
    full_name='DataplaneState.GetInternalIfaces',
    index=2,
    containing_service=None,
    input_type=dataplane__pb2._REQUESTIFACES,
    output_type=dataplane__pb2._REPLYIFACES,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='GetRoutingTables',
    full_name='DataplaneState.GetRoutingTables',
    index=3,
    containing_service=None,
    input_type=google_dot_protobuf_dot_empty__pb2._EMPTY,
    output_type=dataplane__pb2._ROUTESINALLTABLES,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='GetRouteTable',
    full_name='DataplaneState.GetRouteTable',
    index=4,
    containing_service=None,
    input_type=dataplane__pb2._RTABLES,
    output_type=dataplane__pb2._ROUTESINTABLE,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='Getip6tables',
    full_name='DataplaneState.Getip6tables',
    index=5,
    containing_service=None,
    input_type=google_dot_protobuf_dot_empty__pb2._EMPTY,
    output_type=dataplane__pb2._REQUESTIP6TABLERULE,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
])
_sym_db.RegisterServiceDescriptor(_DATAPLANESTATE)

DESCRIPTOR.services_by_name['DataplaneState'] = _DATAPLANESTATE


_CONFIGUREDATAPLANE = _descriptor.ServiceDescriptor(
  name='ConfigureDataplane',
  full_name='ConfigureDataplane',
  file=DESCRIPTOR,
  index=1,
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_start=575,
  serialized_end=857,
  methods=[
  _descriptor.MethodDescriptor(
    name='FlowMark',
    full_name='ConfigureDataplane.FlowMark',
    index=0,
    containing_service=None,
    input_type=dataplane__pb2._REQUESTFLOWMARK,
    output_type=dataplane__pb2._REPLYFLOWMARK,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='CreateRouteTable',
    full_name='ConfigureDataplane.CreateRouteTable',
    index=1,
    containing_service=None,
    input_type=dataplane__pb2._PARFLOWS,
    output_type=dataplane__pb2._REPLYPARFLOWS,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
  _descriptor.MethodDescriptor(
    name='AddIp6tableRule',
    full_name='ConfigureDataplane.AddIp6tableRule',
    index=2,
    containing_service=None,
    input_type=dataplane__pb2._REQUESTIP6TABLERULE,
    output_type=dataplane__pb2._REPLYIP6TABLERULE,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
])
_sym_db.RegisterServiceDescriptor(_CONFIGUREDATAPLANE)

DESCRIPTOR.services_by_name['ConfigureDataplane'] = _CONFIGUREDATAPLANE

# @@protoc_insertion_point(module_scope)
