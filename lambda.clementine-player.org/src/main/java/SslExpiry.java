package org.clementineplayer.lambda;

import com.google.auto.value.AutoValue;
import com.google.common.base.Throwables;
import com.google.common.collect.ImmutableList;
import com.google.common.util.concurrent.Futures;
import com.google.common.util.concurrent.ListenableFuture;
import com.google.common.util.concurrent.ListeningExecutorService;
import com.google.common.util.concurrent.MoreExecutors;

import com.amazonaws.auth.DefaultAWSCredentialsProviderChain;
import com.amazonaws.regions.Region;
import com.amazonaws.regions.Regions;
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.LambdaLogger;
import com.amazonaws.services.sns.AmazonSNSClient;
import com.amazonaws.services.sns.model.PublishRequest;
import com.amazonaws.services.sns.model.PublishResult;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.LineNumberReader;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;

public class SslExpiry {
  private static final String SNS_ARN = "arn:aws:sns:us-east-1:165405240372:ssl_expiry";

  private static final List<String> DOMAINS = ImmutableList.of(
      "buildbot.clementine-player.org",
      "builds.clementine-player.org",
      "data.clementine-player.org",
      "images.clementine-player.org",
      "spotify.clementine-player.org",
      "www.clementine-player.org");

  private final ListeningExecutorService executor = MoreExecutors.listeningDecorator(
      Executors.newFixedThreadPool(2));
  private final AmazonSNSClient snsClient =
        new AmazonSNSClient(new DefaultAWSCredentialsProviderChain());
  private CertificateFactory certFactory;

  public SslExpiry() {
    snsClient.setRegion(Region.getRegion(Regions.US_EAST_1));
    try {
      certFactory = CertificateFactory.getInstance("X.509");
    } catch (CertificateException e) {
      Throwables.propagate(e);
    }
  }

  public String verifyAll(final Context context) throws Exception {
    String ret = verifyAllImpl(new AmazonLogger(context));
    executor.shutdown();
    return ret;
  }

  public String verifyAllImpl(final Logger logger)
      throws InterruptedException, ExecutionException, IOException {
    final ArrayList<ListenableFuture<Result>> futures = new ArrayList<>();
    for (final String domain : DOMAINS) {
      ListenableFuture<Result> future = executor.submit(
          new Callable<Result>() {
            @Override
            public Result call() throws Exception {
              return Result.create(domain, verifyOpenSSL(domain, logger));
            }
          });
      futures.add(future);
    }
    List<Result> results = Futures.allAsList(futures).get();
    StringBuilder sb = new StringBuilder();
    for (Result result : results) {
      sb.append(
          result.domain() + " expires on: " + result.expires().toString() + "\n");
    }
    publishToSNS(sb.toString(), logger);
    return "ok";
  }

  /** Fetch SSL certs using the openssl command line. */
  public Date verifyOpenSSL(String domain, Logger logger) throws IOException, CertificateException {
    Process certFetcher = new ProcessBuilder(
        "openssl", "s_client", "-connect", domain + ":" + 443, "-servername", domain)
        .start();
    try {
      certFetcher.getOutputStream().close();
      LineNumberReader reader =
          new LineNumberReader(new InputStreamReader(certFetcher.getInputStream()));
      String line = null;
      StringBuilder certBuilder = new StringBuilder();
      boolean inCert = false;
      while ((line = reader.readLine()) != null) {
        if (line.equals("-----BEGIN CERTIFICATE-----")) {
          inCert = true;
        }

        if (inCert) {
          certBuilder.append(line);
          certBuilder.append('\n');
        }

        if (line.equals("-----END CERTIFICATE-----")) {
          break;
        }
      }
      String cert = certBuilder.toString();
      X509Certificate x509cert = (X509Certificate) certFactory.generateCertificate(
          new ByteArrayInputStream(cert.getBytes(StandardCharsets.UTF_8)));
      return x509cert.getNotAfter();
    } finally {
      certFetcher.destroyForcibly();
    }
  }

  private void publishToSNS(String message, Logger logger) {
    PublishRequest publishRequest = new PublishRequest()
        .withTopicArn(SNS_ARN)
        .withMessage(message)
        .withSubject("Clementine Domain Certificates Expiry");
    logger.log("created request\n" + publishRequest.toString());
    PublishResult publishResult = snsClient.publish(publishRequest);
    logger.log("Message published: " + publishResult.getMessageId() + "\n");
    logger.log(publishRequest.toString());
  }

  @AutoValue
  abstract static class Result {
    static Result create(String domain, Date expires) {
      return new AutoValue_SslExpiry_Result(domain, expires);
    }

    abstract String domain();
    abstract Date expires();
  }

  private interface Logger {
    void log(String msg);
  }

  private static class AmazonLogger implements Logger {
    private final LambdaLogger logger;

    AmazonLogger(Context context) {
      this.logger = context.getLogger();
    }

    public void log(String msg) {
      logger.log(msg);
    }
  }

  private static class LocalLogger implements Logger {
    public void log(String msg) {
      System.out.println(msg);
    }
  }

  public static void main(String[] args) {
    SslExpiry expiry = new SslExpiry();
    try {
      System.out.println(expiry.verifyAllImpl(new LocalLogger()));
    } catch (Exception e) {
      e.printStackTrace();
    }
    expiry.executor.shutdown();
  }
}
