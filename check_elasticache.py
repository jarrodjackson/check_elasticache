#! /usr/bin/env python
# -*- coding: utf-8 -*-
# vim:fenc=utf-8
#
# Copyright © 2014 Carles Amigó <carles.amigo@socialpoint.es>
#
# Distributed under terms of the MIT license.

"""
Nagios plugin for Amazon ElastiCache monitoring

Somehow inspired from the pmp-check-aws-rds.py script from the Percona
Monitoring Toolkit
"""

import boto.elasticache
import argparse
import sys
import datetime
import json


def get_cluster_info(region, indentifier=None):
    """Function for fetching ElastiCache details"""
    elasticache = boto.elasticache.connect_to_region(region)
    try:
        if indentifier:
            info = elasticache.describe_cache_clusters(
                indentifier,
                show_cache_node_info=True)[
                'DescribeCacheClustersResponse'][
                'DescribeCacheClustersResult'][
                'CacheClusters'][0]
        else:
            info = [v['CacheClusterId']
                    for v in elasticache.describe_cache_clusters()[
                        'DescribeCacheClustersResponse'][
                        'DescribeCacheClustersResult'][
                        'CacheClusters']]
    except boto.exception.BotoServerError:
        info = None
    return info


def get_cluster_stats(node, step, start_time, end_time, metric, indentifier):
    """Function for fetching ElastiCache statistics from CloudWatch"""
    cw = boto.connect_cloudwatch()
    result = cw.get_metric_statistics(step,
                                      start_time,
                                      end_time,
                                      metric,
                                      'AWS/ElastiCache',
                                      'Average',
                                      dimensions={
                                          'CacheClusterId': [indentifier],
                                          'CacheNodeId': ['%04d' % node],
                                          }
                                      )
    if result:
        if len(result) > 1:
            # Get the last point
            result = sorted(result, key=lambda k: k['Timestamp'])
            result.reverse()
        result = float('%.2f' % result[0]['Average'])
    return result


def main():
    """Main function"""

    # Nagios status codes
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3
    short_status = {OK: 'OK',
                    WARNING: 'WARN',
                    CRITICAL: 'CRIT',
                    UNKNOWN: 'UNK'}

    # Cache instance classes as listed on
    # http://aws.amazon.com/elasticache/pricing/
    elasticache_classes = {
        'cache.t2.micro': {'memory': 0.555, 'vcpu': 1},
        'cache.t2.small': {'memory': 1.55, 'vcpu': 1},
        'cache.t2.medium': {'memory': 3.22, 'vcpu': 2},
        'cache.m3.medium': {'memory': 2.78, 'vcpu': 1},
        'cache.m3.large': {'memory': 6.05, 'vcpu': 2},
        'cache.m3.xlarge': {'memory': 13.3, 'vcpu': 4},
        'cache.m3.2xlarge': {'memory': 27.9, 'vcpu': 8},
        'cache.r3.large': {'memory': 13.5, 'vcpu': 2},
        'cache.r3.xlarge': {'memory': 28.4, 'vcpu': 4},
        'cache.r3.2xlarge': {'memory': 58.2, 'vcpu': 8},
        'cache.r3.4xlarge': {'memory': 118, 'vcpu': 16},
        'cache.r3.8xlarge': {'memory': 237, 'vcpu': 32},
        'cache.m1.small': {'memory': 1.3, 'vcpu': 1},
        'cache.m1.medium': {'memory': 3.35, 'vcpu': 1},
        'cache.m1.large': {'memory': 7.1, 'vcpu': 2},
        'cache.m1.xlarge': {'memory': 14.6, 'vcpu': 4},
        'cache.m2.xlarge': {'memory': 16.7, 'vcpu': 2},
        'cache.m2.2xlarge': {'memory': 33.8, 'vcpu': 4},
        'cache.m2.4xlarge': {'memory': 68, 'vcpu': 8},
        'cache.c1.xlarge': {'memory': 6.6, 'vcpu': 8},
        'cache.t1.micro': {'memory': 0.213, 'vcpu': 1}}

    # ElastiCache metrics as listed on
    # http://docs.aws.amazon.com/AmazonCloudWatch/latest/DeveloperGuide/elasticache-metricscollected.html # noqa
    metrics = {'status': 'ElastiCache availability',
               'cpu': 'CPUUtilization',
               'memory': 'FreeableMemory'}

    units = ('percent', 'GB')

    # Parse options
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--region', help='AWS region', required=True)
    parser.add_argument('-l', '--list',
                        help='list of all ElastiCache clusters',
                        action='store_true', default=False,
                        dest='cluster_list')
    parser.add_argument('-i', '--ident', help='ElastiCache cluster identifier')
    parser.add_argument('-p', '--print', help='print status and other ' +
                        'details for a given ElastiCache cluster',
                        action='store_true', default=False, dest='info')
    parser.add_argument('-m', '--metric', help='metric to check: [%s]' %
                        ', '.join(metrics.keys()))
    parser.add_argument('-n', '--node',
                        help='check only specified node number',
                        type=int, default=1)
    parser.add_argument('-w', '--warn', help='warning threshold')
    parser.add_argument('-c', '--crit', help='critical threshold')
    parser.add_argument('-u', '--unit', help='unit of thresholds for "memory" '
                        'metrics: [%s]. Default: percent' % ', '.join(units),
                        default='percent')
    parser.add_argument('--no-threshold-calc', help='in redis do not ' +
                        'calculate the correct threshold acording the number' +
                        ' of cpus', action='store_true', default=False,
                        dest='no_threshold_calc')
    options = parser.parse_args()

    # Check args
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit()
    elif not options.region:
        parser.print_help()
        parser.error('AWS region is not set.')
    elif options.cluster_list:
        info = get_cluster_info(options.region)
        print(json.dumps(info, indent=2))
        sys.exit()
    elif not options.ident:
        parser.print_help()
        parser.error('ElastiCache identifier is not set.')
    elif options.info:
        info = get_cluster_info(options.region, options.ident)
        if info:
            print(json.dumps(info, indent=2))
        else:
            print 'No ElastiCache cluster "%s" found on your AWS account.' % \
                  options.ident
        sys.exit()
    elif not options.metric or options.metric not in metrics.keys():
        parser.print_help()
        parser.error('Metric is not set or not valid.')
    elif not options.warn and options.metric != 'status':
        parser.print_help()
        parser.error('Warning threshold is not set.')
    elif not options.crit and options.metric != 'status':
        parser.print_help()
        parser.error('Critical threshold is not set.')

    tm = datetime.datetime.utcnow()
    status = None
    note = ''
    perf_data = None

    # ElastiCache Status
    if options.metric == 'status':
        info = get_cluster_info(options.region, options.ident)
        if not info:
            status = CRITICAL
            note = 'Unable to get ElastiCache cluster'
        else:
            status = OK
            note = '%s %s. Status: %s' % (info['Engine'],
                   info['EngineVersion'], info['CacheClusterStatus'])

    # ElastiCache Load Average
    elif options.metric == 'cpu':
        info = get_cluster_info(options.region, options.ident)
        if not info:
            status = UNKNOWN
            note = 'Unable to get ElastiCache details and statistics'
        else:
            # Check thresholds
            try:
                warns = [float(x) for x in options.warn.split(',')]
                crits = [float(x) for x in options.crit.split(',')]
                fail = len(warns) + len(crits)
            except:
                fail = 0
            if fail != 6:
                parser.error('Warning and critical thresholds should be 3 ' +
                             'comma separated numbers, e.g. 20,15,10')

            # Because redis only uses 1 cpu, we need to calculate the new
            # thresholds as explained in
            # http://docs.aws.amazon.com/AmazonElastiCache/latest/UserGuide/CacheMetrics.WhichShouldIMonitor.html # noqa
            if not options.no_threshold_calc and info['Engine'] == 'redis':
                warns = [x / elasticache_classes[info['CacheNodeType']]['vcpu']
                         for x in warns]
                crits = [x / elasticache_classes[info['CacheNodeType']]['vcpu']
                         for x in crits]
            cpus = []
            fail = False
            j = 0
            perf_data = []
            for i in [1, 5, 15]:
                if i == 1:
                    # Some stats are delaying to update on CloudWatch.
                    # Let's pick a few points for 1-min cpu avg and get the
                    # last point.
                    n = 5
                else:
                    n = i
                cpu = get_cluster_stats(options.node, i * 60, tm -
                                        datetime.timedelta(
                                            seconds=n * 60),
                                        tm, metrics[options.metric],
                                        options.ident)
                if not cpu:
                    status = UNKNOWN
                    note = 'Unable to get RDS statistics'
                    perf_data = None
                    break
                cpus.append(str(cpu))
                perf_data.append('cpu%s=%s;%s;%s;0;100' % (i, cpu, warns[j],
                                 crits[j]))

                # Compare thresholds
                if not fail:
                    if warns[j] > crits[j]:
                        parser.error('Parameter inconsistency: warning ' +
                                     ' threshold is greater than critical.')
                    elif cpu >= crits[j]:
                        status = CRITICAL
                        fail = True
                    elif cpu >= warns[j]:
                        status = WARNING
                j = j + 1

        if status != UNKNOWN:
            if status is None:
                status = OK
            note = 'Load average: %s%%' % '%, '.join(cpus)
            perf_data = ' '.join(perf_data)

    # RDS Free Storage
    # RDS Free Memory
    elif options.metric in ['memory']:
        # Check thresholds
        try:
            warn = float(options.warn)
            crit = float(options.crit)
        except:
            parser.error('Warning and critical thresholds should be integers.')
        if crit > warn:
            parser.error('Parameter inconsistency: critical threshold is ' +
                         'greater than warning.')
        if options.unit not in units:
            parser.print_help()
            parser.error('Unit is not valid.')

        info = get_cluster_info(options.region, options.ident)
        free = get_cluster_stats(options.node, 60, tm - datetime.timedelta(seconds=60), tm,
                                 metrics[options.metric], options.ident)
        if not info or not free:
            status = UNKNOWN
            note = 'Unable to get ElastiCache details and statistics'
        else:
            if options.metric == 'memory':
                try:
                    storage = elasticache_classes[
                        info['CacheNodeType']]['memory']
                except:
                    print 'Unknown ElastiCache instance class "%s"' % \
                          info.instance_class
                    sys.exit(UNKNOWN)
            free = '%.2f' % (free / 1024 ** 3)
            free_pct = '%.2f' % (float(free) / storage * 100)
            if options.unit == 'percent':
                val = float(free_pct)
                val_max = 100
            elif options.unit == 'GB':
                val = float(free)
                val_max = storage

            # Compare thresholds
            if val <= crit:
                status = CRITICAL
            elif val <= warn:
                status = WARNING

            if status is None:
                status = OK
            note = 'Free %s: %s GB (%.0f%%) of %s GB' % (options.metric,
                                                         free,
                                                         float(free_pct),
                                                         storage)
            perf_data = 'free_%s=%s;%s;%s;0;%s' % (options.metric,
                                                   val,
                                                   warn,
                                                   crit,
                                                   val_max)

    # Final output
    if status != UNKNOWN and perf_data:
        print '%s %s | %s' % (short_status[status], note, perf_data)
    else:
        print '%s %s' % (short_status[status], note)
    sys.exit(status)


if __name__ == '__main__':
    main()
