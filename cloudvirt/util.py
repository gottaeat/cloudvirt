import getpass
import inspect
import logging


def ask_q(query, passwd=False):
    # get the logger of the class that's calling this function
    logger = logging.getLogger(
        inspect.stack()[2].frame.f_locals["self"].__class__.__name__
    )

    # momentarily replace the streamhandler terminator so that we get rid
    # of the ugly newlines when expecting user input
    logging.StreamHandler.terminator = ""
    logger.info("%s: ", query)

    try:
        if passwd:
            response = getpass.getpass(prompt="", stream=None)
        else:
            response = str(input())
    except (EOFError, KeyboardInterrupt):
        print()
        logging.StreamHandler.terminator = "\n"
        logger.error("user cancelled the action, exiting")

    logging.StreamHandler.terminator = "\n"

    return response
