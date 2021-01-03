import { of, race, pipe, concat, iif } from "rxjs";
import { filter, mergeMap, switchMap, delay, share, repeat, take, takeWhile } from "rxjs/operators";
import { cacheContent, monitorContentQuery } from "components/History/caching";
import { singleUpdateResult } from "components/History/caching/db/monitorQuery";
import { fetchDatasetById, fetchDatasetCollectionById, fetchInvocationStepById } from "./fetch";

// prettier-ignore
export const datasetMonitor = (cfg = {}) => {
    // delay gives the monitor a head-start so it can
    // spin up a little before we decide to do an ajax call
    const { spinUpDelay } = cfg;

    return pipe(
        switchMap((id) => createContentMonitor(id, 'dataset', spinUpDelay))
    );
};

export const datasetCollectionMonitor = (cfg = {}) => {
    const { spinUpDelay } = cfg;
    return pipe(switchMap((id) => createContentMonitor(id, "dataset_collection", spinUpDelay)));
};

const createContentMonitor = (id, contentType, spinUpDelay = 250) => {
    let fetcher;
    switch (contentType) {
        case "dataset":
            fetcher = fetchDatasetById;
            break;
        case "dataset_collection":
            fetcher = fetchDatasetCollectionById;
            break;
        default:
            console.error(`Can't create monitor for ${contentType}-${id}`);
    }
    return createMonitor(id, contentType, fetcher, spinUpDelay);
};

const buildPouchRequest = (id, contentType) => {
    return {
        selector: {
            id: { $eq: id },
            history_content_type: contentType,
        },
    };
};

// prettier-ignore
const createMonitor = (id, contentType, fetcher, spinUpDelay = 250) => {
    // build the pouchdb/mongo request, which is a selector
    // and limits, offsets, etc

    // retrieve changes from cache
    const changes$ = of(buildPouchRequest(id, contentType)).pipe(
        monitorContentQuery(),
        singleUpdateResult(),
        share()
    );

    // cache results that reflect non-deleted existing data in the cache
    const existing$ = changes$.pipe(
        filter(Boolean),
        );

    // load and cache dataset from server then switch over to the monitor
    const fetchItem$ = of(id).pipe(
        delay(spinUpDelay),
        fetcher(),
        mergeMap((rawJson) => cacheContent(rawJson, true))
    );

    // let the monitor and the ajax call race, first one wins
    const firstValue$ = race(fetchItem$, existing$).pipe(take(1));

    return concat(firstValue$, changes$);
};

const TERMINAL_JOB_STATES = ["ok", "error", "deleted", "paused"];
const stepIsTerminal = (step) =>
    ["scheduled", "cancelled", "failed"].includes(step.state) &&
    step.jobs.every((job) => TERMINAL_JOB_STATES.includes(job.state));

const createInvocationStepMonitor = (id) => {
    const initialFetch$ = of(id).pipe(fetchInvocationStepById());
    const pollingFetch$ = of(id).pipe(
        delay(3000),
        fetchInvocationStepById(),
        repeat(),
        // takeWhile cancels source on true, so also cancels repeat
        takeWhile((val) => !stepIsTerminal(val), true)
    );
    return initialFetch$.pipe(
        // poll only if initial status is non-terminal
        mergeMap((val) => iif(() => stepIsTerminal(val), of(val), pollingFetch$))
    );
};

export const invocationStepMonitor = () => pipe(switchMap((id) => createInvocationStepMonitor(id)));
