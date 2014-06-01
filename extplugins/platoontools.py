# -*- coding: utf-8 -*-

# PlatoonTools plugin for BigBrotherBot(B3)
# Copyright (c) 2014 Harry Gabriel <rootdesign@gmail.com>
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
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import b3
from b3.plugin import Plugin
from b3.clients import Client, Group
import b3.events
from threading import Thread
import json
from urllib2 import Request, urlopen, URLError
from ConfigParser import NoOptionError

__version__ = '0.0.1'
__author__ = 'ozon'


class PlatoontoolsPlugin(Plugin):
    _admin_plugin = None
    platoons = {}
    default_platoon_settings = {
        'member_group': 'mod',
        'leader_group': 'mod',
        'admin_group': 'admin',
    }

    def onLoadConfig(self):
        # setup platoons and load settings
        for section in self.config.sections():
            if section != 'settings':
                self.platoons.update({
                    section: {
                        'data': None,
                        'settings': self.default_platoon_settings
                    }
                })

                try:
                    self.platoons[section]['settings']['member_group'] = self.config.get(section, 'member_group')
                except NoOptionError:
                    self.warning('could not find settings/member_group for platoon id %s in config file, '
                                 'using default: %s' % (section, self.default_platoon_settings['member_group']))
                try:
                    self.platoons[section]['settings']['leader_group'] = self.config.get(section, 'leader_group')
                except NoOptionError:
                    self.warning('could not find settings/leader_group for platoon id %s in config file, '
                                 'using default: %s' % (section, self.default_platoon_settings['leader_group']))
                try:
                    self.platoons[section]['settings']['admin_group'] = self.config.get(section, 'admin_group')
                except NoOptionError:
                    self.warning('could not find settings/admin_group for platoon id %s in config file, '
                                 'using default: %s' % (section, self.default_platoon_settings['admin_group']))

        # first platoon update
        self.do_platoon_update()

    def onStartup(self):
        # load the admin plugin
        self._admin_plugin = self.console.getPlugin('admin')

        # check game parser
        if self.console.game.gameName != 'bf4':
            self.error('This plugin needs a BF4 game server.')
            raise SystemExit(220)

        # register event "Client Connect"
        self.registerEvent(b3.events.EVT_CLIENT_AUTH)

    def onEvent(self, event):
        if event.type == b3.events.EVT_CLIENT_AUTH:
            self._update_client_group(event.client)

    def _get_platoon_member(self, client):
        for p_id, platoon in self.platoons.items():
            if client.name in platoon['data']['members']:
                return platoon['data']['members'][client.name]

    def _update_client_group(self, client):
        """Update the group for the given client"""
        platoon_member = self._get_platoon_member(client)
        if platoon_member:
            # get b3 group keyword for the platoon member
            group = Group(keyword=self.platoons[platoon_member['platoon_id']]['settings']['member_group'])
            if platoon_member['is_admin']:
                group = Group(keyword=self.platoons[platoon_member['platoon_id']]['settings']['admin_group'])
            elif platoon_member['is_leader']:
                group = Group(keyword=self.platoons[platoon_member['platoon_id']]['settings']['leader_group'])
            #elif platoon_member['is_founder']:
            #    group = Group(keyword=self.platoons[platoon_member['platoon_id']]['settings']['founder_group'])

            # get group from storage
            group = self.console.storage.getGroup(group)

            # put client in group
            if not client.inGroup(group) and not client.maxLevel >= group.level:
                self.debug('Put %s in group %s' % (client.name, group.name))
                client.setGroup(group)
                client.save()

    def callback_platoon_update(self, platoon_id, data):
        raw_data = data.get('globalContext').get('club')
        if raw_data:
            self.info('Update platoon [%s] - %s' % (raw_data.get('tag'), raw_data.get('name')))

            if raw_data.get('status') == 'applyinvite':
                self.warning('Everyone can join the platoon "%s" without invitation! '
                             'For safe use, new members should join by invitation only.' % raw_data.get('name'))

            platoon_members = raw_data.get('founders') + raw_data.get('leaders') + raw_data.get('members')
            admin_ids = raw_data.get('adminIds')
            founder_ids = [f.get('userId') for f in raw_data.get('founders')]
            leader_ids = [f.get('userId') for f in raw_data.get('leaders')]
            members = dict()

            for member in platoon_members:
                members[member.get('user').get('username')] = dict(
                    name=member.get('user').get('username'),
                    user_id=member.get('user').get('userId'),
                    level=member.get('level'),
                    joined=member.get('joinedDate'),
                    is_admin=True if member.get('user').get('userId') in admin_ids else False,
                    is_founder=True if member.get('user').get('userId') in founder_ids else False,
                    is_leader=True if member.get('user').get('userId') in leader_ids else False,
                    platoon_id=member.get('clubId')
                )

            self.platoons[platoon_id]['data'] = {
                'name': raw_data.get('name'),
                'tag': raw_data.get('tag'),
                'admin_ids': admin_ids,
                'members': members,
                'status': raw_data.get('status')
            }

        # update connected clients
        [self._update_client_group(client) for client in self.console.clients.getList()]

    def do_platoon_update(self):
        for p_id in self.platoons.keys():
            self.debug('Fetch data from battlelog for platoon id: %s' % p_id)
            BattlelogQuery(platoon_id=p_id, callback=self.callback_platoon_update, callback_args=(p_id,)).start()


class BattlelogQuery(Thread):
    def __init__(self, name=None, platoon_id=None, callback=None, callback_args=()):
        Thread.__init__(self, name=name, )
        self.__platoon_id = platoon_id
        self.__callback = callback
        self.__callback_args = callback_args

    def run(self):
        platoon_raw_data = self.fetch_data()

        if self.__callback:
            self.__callback(*self.__callback_args, data=platoon_raw_data)

    def fetch_data(self):
        url = 'http://battlelog.battlefield.com/bf4/en/platoons/members/%s/' % self.__platoon_id
        headers = {'X-Requested-With': 'XMLHttpRequest', 'X-AjaxNavigation': '1'}

        req = Request(url, '', headers)
        try:
            response = urlopen(req)
        except URLError as e:
            print e.reason
        else:
            return json.load(response)


if __name__ == '__main__':
    from b3.fake import fakeConsole, superadmin, joe, simon, fakeAdminPlugin
    import time

    myplugin = PlatoontoolsPlugin(fakeConsole, 'extplugins/conf/plugin_platoontools.ini')
    myplugin.console.game.gameName = 'bf4'
    myplugin.onStartup()
    myplugin.onLoadConfig()
    time.sleep(2)

    myplugin.console.game.gameType = 'Domination0'
    myplugin.console.game._mapName = 'XP2_Skybar'
    superadmin.connects(cid=0)
    # make joe connect to the fake game server on slot 1
    joe.connects(cid=1)
    # make joe connect to the fake game server on slot 2
    simon.connects(cid=2)
    # superadmin put joe in group user
    #superadmin.says('!putgroup joe user')
    superadmin.says('!putgroup simon user')

    joe.name = 'O2ON'

    superadmin.connects(cid=0)