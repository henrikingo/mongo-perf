#!/usr/bin/env python
from argparse import ArgumentParser, RawTextHelpFormatter
from subprocess import Popen, PIPE, call
import datetime
import sys
import json
import urllib2
import os



class MongoShellCommandError(Exception):
    """ Raised when the mongo shell comes back with an unexpected error
    """

def parse_arguments():
    usage = "python benchrun.py -f <list of test files> -t <list of thread counts>\n       run with --help for argument descriptions"
    parser = ArgumentParser(description="mongo-perf micro-benchmark utility", usage=usage, formatter_class=RawTextHelpFormatter)

    parser.add_argument('-f', '--testfiles', dest='testfiles', nargs="+",
                        help='Provide a list of js test files to run',
                        default=None)
    parser.add_argument('-t', '--threads', dest='threads', nargs="+",
                        help='Specify which thread configuration to use',
                        type=int, default=[1, 2, 4, 8, 12, 16])
    parser.add_argument('-m', '--multidb', dest='multidb',
                        help='Specify how many databases the test should use',
                        type=int, default=1)
    parser.add_argument('-c', '--multicoll', dest='multicoll',
                        help='Specify how many collections the test should use',
                        type=int, default=1)
    parser.add_argument('--trialTime', dest='seconds',
                        help='Specify how many seconds to run each trial',
                        type=int, default=5)
    parser.add_argument('--trialCount', dest='trials',
                        help='Specify how many trials to run',
                        type=int, default=1)
    parser.add_argument('--host', dest='hostname',
                        help='hostname of the mongod/mongos under test',
                        default='localhost')
    parser.add_argument('--port', dest='port',
                        help='Port of the mongod/mongos under test',
                        default='27017')
    parser.add_argument('--replset', dest='replica_set',
                        help='replica set name of the mongod/mongos under test',
                        default=None)
    parser.add_argument('-u', '--username', dest='username',
                        help='username to use for mongodb authentication',
                        default=None)
    parser.add_argument('-p', '--password', dest='password',
                        help='password to use for mongodb authentication',
                        default=None)
    parser.add_argument('--shard', dest='shard',
                        help='Specify shard cluster the test should use, 0 - no shard, 1 - shard with {_id: hashed}, 2 - shard with {_id: 1}',
                        type=int, default=0, choices=[0, 1, 2])
    parser.add_argument('-s', '--shell', dest='shellpath',
                        help="Path to the mongo shell executable to use.",
                        default='mongo')
    parser.add_argument('--safe', dest='safeMode',
                        nargs='?', const='true', choices=['true', 'false'],
                        help='this option enables a call to GLE after every op instead of every 100 ops',
                        default='false')
    parser.add_argument('-w', dest='w',
                        help='w write concern',
                        type=int, default=0)
    parser.add_argument('-j', dest='j',
                        nargs='?', const='true', choices=['true', 'false'],
                        help='this option turns on the j write concern',
                        default='false')
    parser.add_argument('--writeCmd', dest='writeCmd',
                        nargs='?', const='true', choices=['true', 'false'],
                        help='this option turns on use of the write commands instead of legacy write operations',
                        default='true')
    parser.add_argument('--readCmd', dest='readCmd',
                        nargs='?', const='true', choices=['true', 'false'],
                        help='this option turns on use of the read commands instead of legacy read operations',
                        default='false')

    parser.add_argument('--includeFilter', dest='includeFilter', nargs='+', action="append",
                        help="Run just the specified tests/suites. Can specify multiple tags per --includeFilter\n"
                        "flag. All tests/suites matching any of the tags will be run.\n"
                        "Can specify multiple --includeFilter flags on the command line. A test\n"
                        "must match all the --includeFilter clauses in order to be run.\n\n"
                        "Ex 1: --includeFilter insert remove  --includeFilter core \n"
                        "       will run all tests tagged with (\"insert\" OR \"remove\") AND (\"core\").\n"
                        "Ex 2: --includeFilter %%\n"
                        "       will run all tests",
                        default=[])
    parser.add_argument('--excludeFilter', dest='excludeFilter', nargs='+', action="append",
                        help="Exclude tests matching all of the tags included.\n"
                        "Can specify multiple --excludeFilter flags on the command line. A test\n"
                        "matching any --excludeFilter clauses will not be run.\n"
                        "A test that is both included according to --includeFilter and excluded by --excludeFilter,\n"
                        "will not be run.\n\n"
                        "Ex: --excludeFilter slow old --excludeFilter broken \n"
                        "     will exclude all tests tagged with (\"slow\" AND \"old\") OR (\"broken\").",
                        default=[])
    parser.add_argument('--out', dest='outfile',
                        help='write the results as json to the specified file')
    parser.add_argument('--exclude-testbed', dest='excludeTestbed', nargs='?', const='true',
                        choices=['true','false'], default='false',
                        help='Exclude testbed information from results file')
    parser.add_argument('--printArgs', dest='printArgs', nargs='?', const='true',
                        choices=['true','false'], default='false',
                        help='Print the benchrun args before running the test.')
    return parser


def load_file_in_shell(subproc, file, echo=True):
    cmd = "load('%s')\n" % file
    if echo:
        print(cmd)
    subproc.stdin.write(cmd)
    line = subproc.stdout.readline().strip()
    if line != "true":
        raise MongoShellCommandError("unable to load file %s message was %s"
                                     % (file, line))


def main():
    parser = parse_arguments()
    args = parser.parse_args()

    if not args.testfiles:
        print("Must provide at least one test file."
              " Run with --help for details.")
        sys.exit(1)

    for testfile in args.testfiles:
        if not os.path.exists(testfile):
            print("A test file that was passed in does not exist: %s"
                  % testfile)
            sys.exit(1)

    if args.multidb < 1:
        print("MultiDB option must be greater than zero. Will be set to 1.")
        args.multidb = 1

    if args.multicoll < 1:
        print("MultiCollection option must be greater than zero."
              " Will be set to 1.")
        args.multicoll = 1

    if args.shard < 0:
        print("shard option must be [0, 2]. Will be set to 0.")
        args.shard = 0
    elif args.shard > 2:
        print("shard option must be [0, 2] . Will be set to 2.")
        args.shard = 2

    if args.includeFilter == [] :
        args.includeFilter = '%'
    elif len(args.includeFilter) == 1 :
        args.includeFilter = args.includeFilter[0]
        if args.includeFilter == ['%'] :
            args.includeFilter = '%'

    # Print version info.
    if args.username:
        auth = ["-u", args.username, "-p", args.password]
    else:
        auth = []

    print(auth)
    call([args.shellpath, "--norc", "--port", args.port, "--eval",
            "print('db version: ' + db.version());"
            " db.serverBuildInfo().gitVersion;"] + auth)
    print("")


    # Open a mongo shell subprocess and load necessary files.
    mongo_proc = Popen([args.shellpath, "--norc", "--quiet", "--port", args.port] + auth, 
                       stdin=PIPE, stdout=PIPE)

    # load test files
    load_file_in_shell(mongo_proc, 'util/utils.js')
    for testfile in args.testfiles:
        load_file_in_shell(mongo_proc, testfile)

    # put all crud options in a Map
    crud_options = {}
    crud_options["safeGLE"] = args.safeMode
    crud_options["writeConcern"] = {}
    if (args.j):
            crud_options["writeConcern"]["j"] = args.j
    if (args.w):
            crud_options["writeConcern"]["w"] = args.w
    crud_options["writeCmdMode"] = args.writeCmd
    crud_options["readCmdMode"] = args.readCmd

    cmdstr = ("mongoPerfRunTests(" +
              str(args.threads) + ", " +
              str(args.multidb) + ", " +
              str(args.multicoll) + ", " +
              str(args.seconds) + ", " +
              str(args.trials) + ", " +
              str(json.dumps(args.includeFilter)) + ", " +
              str(json.dumps(args.excludeFilter)) + ", " +
              str(args.shard) + ", " +
              str(json.dumps(crud_options)) + ", " + 
              str(args.excludeTestbed) + "," + 
              str(args.printArgs) +  "," +
              str(args.username) + "," +
              str(args.password) +
              ");\n")
    mongo_proc.stdin.write(cmdstr)
    print cmdstr
    mongo_proc.stdin.close()

    # Read test output.
    readout = False
    getting_results = False
    got_results = False
    line_results = ""
    for line in iter(mongo_proc.stdout.readline, ''):
        line = line.strip()
        if line == "@@@START@@@":
            readout = True
            getting_results = False
        elif line == "@@@END@@@":
            readout = False
            getting_results = False
        elif line == "@@@RESULTS_START@@@":
            readout = False
            getting_results = True
        elif line == "@@@RESULTS_END@@@":
            readout = False
            got_results = True
            getting_results = False
        elif readout:
            print line
        elif not got_results and getting_results:
            line_results += line

    print("Finished Testing.")
    results_parsed = json.loads(line_results)
    if args.outfile:
        out = open(args.outfile, 'w')
        json.dump(results_parsed, out, indent=4, separators=(',', ': '))
        out.close()
    else:
        print json.dumps(results_parsed, indent=4, separators=(',', ': '))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        sys.stderr.write(str(e))
        sys.exit(1)
    sys.exit(0)

