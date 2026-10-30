# IPSet classes for dynft.  Provide abstracted classes for defining an IP Set,
# and it's member elements, for use with dynft.  Includes the production of
# libnftables-json valid blobs of JSON that can be included in cmd exectuted by
# libnftables.
# 
# Copyright (C) 2024  Dameon Wagner
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from dns.resolver import Resolver, NoAnswer, NXDOMAIN
from netaddr import IPAddress

##############################################################################
# Module constants
#
ALLOWED_FAMILY = ( 'inet', 'ip6', 'ip' )
ALLOWED_TYPES  = ( 'ipv6_addr', 'ipv4_addr' )


##############################################################################
# Helper functions
#

def ipset_element_factory(members, addr_family='ipv4_addr'):
    """Take a set members from config, and return a list of IPSetElement
    objects for use as an IPSet object's elements property.
    """
    resolver = Resolver()
    elements = []

    if addr_family == 'ipv6_addr':
        _rrtype = 'AAAA'
        _inet_family = 6
    elif addr_family == 'ipv4_addr':
        _rrtype = 'A'
        _inet_family = 4
    
    for member in members:
        if member.get('literal') and not member.get('host'):
            literal = IPAddress(member.get('literal'))
            if literal.version == _inet_family: 
                try:
                    rev_dns = resolver.query(literal.reverse_dns, 'PTR')[0].to_text()
                except NXDOMAIN:
                    rev_dns = 'IP-LITERAL'
                elements.append(IPSetElement(dict(
                    val=str(literal), comment=rev_dns
                )))
        elif member.get('host') and not member.get('literal'):
            try:
                addrs = resolver.query(member.get('host'), _rrtype)
            except NoAnswer:
                addrs = []
            except NXDOMAIN:
                continue
            else:
                for addr in addrs:
                    elements.append(IPSetElement(dict(
                        val=addr.address, comment=member.get('host')
                    )))

    return elements
# ipset_element_factory()

##############################################################################
# Defined classes
#

class IPSetElement:
    """
    A class to represent an nftables set element, as described for the "ELEM"
    libnftables-json(5).

    Properties:
        "val": The active value of a set element, commonly a Layer3 address
            (IPv6 or IPv4).
        "comment": An optional comment, used to provide a more friendly
            reminder of the FQDN related to the Layer3 address
    """

    def __init__(self, member):
        self._comment = member.get('comment')
        self._val     = member.get('val')

    @property
    def val(self):
        return self._val

    @property
    def comment(self):
        return self._comment

    def serialize_cmd(self):
        """Return an "elem" blob of JSON for inclusion in a nftables
        `json_cmd()`.
        """
        serialize_cmd = dict(elem=dict(
            val=self.val,
            comment=self.comment
        ))
        return serialize_cmd

    def __repr__(self):
        return 'IPSetElement: <{}: {}>'.format(self.comment, self.val)
# class:IPSetElement


class IPSet:
    """
    A class to represent an nftables set, as described for the "SET" object in
    libnftables-json(5).

    Properties:
        "name": The descriptive name for the set object, see nft(8) for the
            lexical conventions of naming, and valid character sets.
        "family": The address family for the table that contains the set.
            Valid options are: 'inet', 'ip6', or 'ip'.
        "table": The name of the table that contains the set.
        "type": The data type of elements contained by the set.  Currently
            supported options are: 'ipv6_addr', or 'ipv4_addr'.
        "elements": A list of `IPSetElement` objects, to represent the set's
            member elements.
    """

    def __init__(self, ipset, name=None, family='inet', table='filter', type='ipv4_addr'):
        self._name = name
        if self._name == None:
            raise IPSetException('Set has no provided name',
                IPSetException.NO_NAME)
        
        self._family = ipset.get('family') or family
        if self._family not in ALLOWED_FAMILY:
            raise IPSetException(
                'Set family "{}" is not valid or supported'.format(self._family),
                IPSetException.INVALID_FAMILY
            )
        
        self._table = ipset.get('table') or table
        
        self._type = ipset.get('type') or type
        if self._type not in ALLOWED_TYPES:
            raise IPSetException(
                'Set type "{}" is not valid or supported'.format(self._type),
                IPSetException.INVALID_TYPE
            )
        elif (self._family,self._type) in (('ip','ipv6_addr'),('ip6','ipv4_addr')):
            raise IPSetException(
                'Set type "{}" is mismatched with family "{}"'.format(
                    self._type, self._family),
                IPSetException.FAMILY_TYPE_MISMATCH
            )
        
        self._elements = []
        self._elements = ipset_element_factory(ipset.get('members'), self.type)
    # IPSet.__init__()
    
    @property
    def name(self):
        return self._name

    @property
    def family(self):
        return self._family

    @property
    def table(self):
        return self._table

    @property
    def type(self):
        return self._type

    @property
    def elements(self):
        return self._elements

    def __repr__(self):
        return 'IPSet: <{}: {}>'.format(self.name, self.elements)

    def _cmd_stub(self):
        """Generic function to provide the common boilerplate JSON command stub
        for use with libnfables' `json_cmd()` function.
        """
        cmd_stub = dict(set={})
        cmd_stub['set'].update(dict(
            name=self.name, family=self.family,
            table=self.table, type=self.type
        ))
        return cmd_stub

    def flush_cmd(self):
        """Simple extension of _cmd_stub(), which will flush cause the removal
        of all elements in the set.
        """
        flush_cmd = dict(flush=self._cmd_stub())
        return flush_cmd

    def add_cmd(self):
        """Generate a JSON blob that will result in the addition of the
        object's elements to the related set in the nftables ruleset.  It will
        also cause the creation of the set if it does not already exist.
        """
        add_cmd = dict(add=self._cmd_stub())

        add_elements = [ e.serialize_cmd() for e in self._elements ]
        if len(add_elements):
            add_cmd['add']['set'].update(dict(elem = add_elements))
        return add_cmd
# class:IPSet


##############################################################################
# Exception classes
#

class IPSetException(Exception):
    NO_NAME              = 32
    INVALID_FAMILY       = 33
    INVALID_TYPE         = 34
    FAMILY_TYPE_MISMATCH = 35

    def __init__(self, msg, errno=255):
        self.msg = msg
        self.errno = errno
# class:IPSetException
