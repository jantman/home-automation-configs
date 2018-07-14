#!/usr/bin/perl  -T
#
# ==========================================================================
#
# HEAVILY HACKED-UP VERSION OF the below, from
# https://github.com/pliablepixels/zmeventserver
# modifications by Jason Antman -
#    https://github.com/jantman/home-automation-configs
#
# All websockets and other fancy-ness ripped out. What remains just polls
# ZoneMinder shared memory for new events every 3 seconds, and runs a command
# when one is found.
#
# ==========================================================================
#
# ZoneMinder Realtime Notification System
#
# A  light weight event notification daemon
# Uses shared memory to detect new events (polls SHM)
# Also opens a websocket connection at a configurable port
# so events can be reported
# Any client can connect to this web socket and handle it further
# for example, send it out via APNS/GCM or any other mechanism
#
# This is a much  faster and low overhead method compared to zmfilter
# as there is no DB overhead nor SQL searches for event matches

# ~ PP
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
# ==========================================================================

use strict;
use bytes;

# Declare options.
my $verbose                    = 0;
my $event_check_interval       = 3; # seconds
my $monitor_reload_interval    = 300; # seconds
my $read_alarm_cause           = 0;
my $tag_alarm_event_id         = 0;
my $handlerPath                = "/usr/local/bin/zmevent_handler.py";

my $dummyEventTest = 0; # if on, will generate dummy events. Not in config for a reason. Only dev testing
my $dummyEventInterval = 30; # timespan to generate events in seconds
my $dummyEventTimeLastSent = time();

# This part makes sure we have the right deps
if (!try_use ("File::Basename")) {Fatal ("File::Basename missing");}
if (!try_use ("File::Spec")) {Fatal ("File::Spec missing");}
if (!try_use ("Crypt::MySQL qw(password password41)")) {Fatal ("Crypt::MySQL  missing");}
if (!try_use ("JSON"))
{
    if (!try_use ("JSON::XS"))
    { Fatal ("JSON or JSON::XS  missing");exit (-1);}
}

my $notId = 1;

# this is just a wrapper around Config::IniFiles val
# older versions don't support a default parameter
sub config_get_val {
    my ( $config, $sect, $parm, $def ) = @_;
    my $val = $config->val($sect, $parm);
    return defined($val)? $val:$def;
}

sub true_or_false {
  return $_[0] ? "true" : "false";
}

sub value_or_undefined {
  return $_[0] || "(undefined)";
}

sub present_or_not {
  return $_[0] ? "(defined)" : "(undefined)";
}

# ==========================================================================
#
# Don't change anything below here
#
# ==========================================================================

use lib '/usr/local/lib/x86_64-linux-gnu/perl5';
use ZoneMinder;
use POSIX;
use DBI;
use Data::Dumper;

$| = 1;

$ENV{PATH}  = '/bin:/usr/bin';
$ENV{SHELL} = '/bin/sh' if exists $ENV{SHELL};
delete @ENV{qw(IFS CDPATH ENV BASH_ENV)};

sub Usage
{
        print( "This daemon is not meant to be invoked from command line\n");
    exit( -1 );
}

logInit();
logSetSignal();

my $dbh = zmDbConnect();
my %monitors;
my $monitor_reload_time = 0;
my $apns_feedback_time = 0;
my $proxy_reach_time=0;
my $wss;
my @events=();
my @active_connections=();
my $alarm_header="";
my $alarm_mid="";
my $alarm_eid="";

# MAIN

Info( "Event Notification daemon starting\n" );
my $res;
while (1) {
  $res = checkEvents();
  printdbg("Result: $res");
  foreach my $evt (@events) {
    Info( "Event: " . Dumper($evt) );
    printdbg("calling $handlerPath");
    system("$handlerPath -E $evt->{EventId} -M $evt->{MonitorId} -C '$evt->{Cause}' &");
  }
  sleep $event_check_interval;
}
Info( "Event Notification daemon exiting\n" );
exit();

# Try to load a perl module
# and if it is not available
# generate a log
sub try_use
{
  my $module = shift;
  eval("use $module");
  return($@ ? 0:1);
}

# console print
sub printdbg
{
	my $a = shift;
    my $now = strftime('%Y-%m-%d,%H:%M:%S',localtime);
    print($now," ",$a, "\n") if $verbose;
}

# This function uses shared memory polling to check if
# ZM reported any new events. If it does find events
# then the details are packaged into the events array
# so they can be JSONified and sent out
sub checkEvents()
{
    my $eventFound = 0;
    if ( (time() - $monitor_reload_time) > $monitor_reload_interval )
    {
        Debug ("Reloading Monitors...");
        foreach my $monitor (values(%monitors))
        {
            zmMemInvalidate( $monitor );
        }
        loadMonitors();
    }
    @events = ();
    $alarm_header = "";
    $alarm_mid="";
    $alarm_eid = ""; # only take 1 if several occur
    foreach my $monitor ( values(%monitors) )
    {
         my $alarm_cause="";

         my ( $state, $last_event, $trigger_cause, $trigger_text)
            = zmMemRead( $monitor,
                 [ "shared_data:state",
                   "shared_data:last_event",
                   "trigger_data:trigger_cause",
                   "trigger_data:trigger_text",
                 ]
            );
        if ($state == STATE_ALARM || $state == STATE_ALERT)
        {
            Debug ("state is STATE_ALARM or ALERT for ".$monitor->{Name});
            if ( !defined($monitor->{LastEvent})
                         || ($last_event != $monitor->{LastEvent}))
            {
                $alarm_cause=zmMemRead($monitor,"shared_data:alarm_cause") if ($read_alarm_cause);
                $alarm_cause = $trigger_cause if (defined($trigger_cause) && $alarm_cause eq "" && $trigger_cause ne "");
                printdbg ("Unified Alarm details: $alarm_cause");
                Info( "New event $last_event reported for ".$monitor->{Name}." ".$alarm_cause."\n");
                $monitor->{LastState} = $state;
                $monitor->{LastEvent} = $last_event;
                my $name = $monitor->{Name};
                my $mid = $monitor->{Id};
                my $eid = $last_event;
                Debug ("Creating event object for ".$monitor->{Name}." with $last_event");
                push @events, {Name => $name, MonitorId => $mid, EventId => $last_event, Cause=> $alarm_cause};
                $alarm_eid = $last_event;
                $alarm_header = "Alarms: " if (!$alarm_header);
                $alarm_header = $alarm_header . $name ;
                $alarm_header = $alarm_header." ".$alarm_cause if (defined $alarm_cause);
                $alarm_header = $alarm_header." ".$trigger_cause if (defined $trigger_cause);
                $alarm_mid = $alarm_mid.$mid.",";
                $alarm_header = $alarm_header . " (".$last_event.") " if ($tag_alarm_event_id);
                $alarm_header = $alarm_header . "," ;
                $eventFound = 1;
            }

        }
    }
    chop($alarm_header) if ($alarm_header);
    chop ($alarm_mid) if ($alarm_mid);

    # Send out dummy events for testing
    if (!$eventFound && $dummyEventTest && (time() - $dummyEventTimeLastSent) >= $dummyEventInterval ) {
        $dummyEventTimeLastSent = time();
        my $random_mon = $monitors{(keys %monitors)[rand keys %monitors]};
        Info ("Sending dummy event to: ".$random_mon->{Name});
        push @events, {Name => $random_mon->{Name}, MonitorId => $random_mon->{Id}, EventId => $random_mon->{LastEvent}, Cause=> "Dummy"};
        $alarm_header = "Alarms: Dummy alarm at ".$random_mon->{Name};
        $alarm_mid = $random_mon->{Id};
        $eventFound = 1;

    }

    return ($eventFound);
}

# Refreshes list of monitors from DB
#
sub loadMonitors
{
    Debug ( "Loading monitors\n" );
    $monitor_reload_time = time();

    my %new_monitors = ();

    my $sql = "SELECT * FROM Monitors
               WHERE find_in_set( Function, 'Modect,Mocord,Nodect' )".
               ( $Config{ZM_SERVER_ID} ? 'AND ServerId=?' : '' );
    Debug ("SQL to be executed is :$sql");
     my $sth = $dbh->prepare_cached( $sql )
        or Fatal( "Can't prepare '$sql': ".$dbh->errstr() );
    my $res = $sth->execute( $Config{ZM_SERVER_ID} ? $Config{ZM_SERVER_ID} : () )
        or Fatal( "Can't execute: ".$sth->errstr() );
    while( my $monitor = $sth->fetchrow_hashref() )
    {
        if ( !zmMemVerify( $monitor ) ) {
              zmMemInvalidate( $monitor );
              next;
        }
       # next if ( !zmMemVerify( $monitor ) ); # Check shared memory ok

        if ( defined($monitors{$monitor->{Id}}->{LastState}) )
        {
            $monitor->{LastState} = $monitors{$monitor->{Id}}->{LastState};
        }
        else
        {
            $monitor->{LastState} = zmGetMonitorState( $monitor );
        }
        if ( defined($monitors{$monitor->{Id}}->{LastEvent}) )
        {
            $monitor->{LastEvent} = $monitors{$monitor->{Id}}->{LastEvent};
        }
        else
        {
            $monitor->{LastEvent} = zmGetLastEvent( $monitor );
        }
        $new_monitors{$monitor->{Id}} = $monitor;
    }
    %monitors = %new_monitors;
}

# Checks if the monitor for which
# an alarm occurred is part of the monitor list
# for that connection
sub getInterval
{
    my $intlist = shift;
    my $monlist = shift;
    my $mid = shift;

    #print ("getInterval:MID:$mid INT:$intlist AND MON:$monlist\n");
    my @ints = split (',',$intlist);
    my @mids = split (',',$monlist);
    my $idx = -1;
    foreach (@mids)
    {
        $idx++;
        #print ("Comparing $mid with $_\n");
        if ($mid eq $_)
        {
            last;
        }
    }
    #print ("RETURNING index:$idx with Value:".$ints[$idx]."\n");
    return $ints[$idx];

}

# Checks if the monitor for which
# an alarm occurred is part of the monitor list
# for that connection
sub isInList
{
    my $monlist = shift;
    my $mid = shift;

    my @mids = split (',',$monlist);
    my $found = 0;
    foreach (@mids)
    {
        if ($mid eq $_)
        {
            $found = 1;
            last;
        }
    }
    return $found;

}
