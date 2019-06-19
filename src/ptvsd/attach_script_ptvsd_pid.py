def attach(port, host, client, log_dir):
    try:
        if not log_dir:
            log_dir = None

        import ptvsd.options
        ptvsd.options.log_dir = log_dir
        ptvsd.options.client = client
        ptvsd.options.host = host
        ptvsd.options.port = port

        import ptvsd.log
        ptvsd.log.to_file()
        ptvsd.log.info("Debugger successfully injected")

        if ptvsd.options.client:
            from ptvsd._remote import attach
            attach((host, port))
        else:
            ptvsd.enable_attach((host, port))

    except:
        import traceback
        traceback.print_exc()
